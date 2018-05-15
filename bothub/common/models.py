import uuid
import base64

from django.db import models
from django.utils.translation import gettext as _
from django.utils import timezone

from bothub.authentication.models import User

from . import languages
from .exceptions import RepositoryUpdateAlreadyStartedTraining
from .exceptions import RepositoryUpdateAlreadyTrained
from .exceptions import TrainingNotAllowed
from .exceptions import DoesNotHaveTranslation


class RepositoryCategory(models.Model):
    class Meta:
        verbose_name = _('repository category')
        verbose_name_plural = _('repository categories')

    name = models.CharField(
        _('name'),
        max_length=32)

    def __str__(self):
        return self.name


class Repository(models.Model):
    class Meta:
        verbose_name = _('repository')
        verbose_name_plural = _('repositories')
        unique_together = ['owner', 'slug']

    CATEGORIES_HELP_TEXT = _('Categories for approaching repositories with ' +
                             'the same purpose')
    DESCRIPTION_HELP_TEXT = _('Tell what your bot do!')

    uuid = models.UUIDField(
        _('UUID'),
        primary_key=True,
        default=uuid.uuid4,
        editable=False)
    owner = models.ForeignKey(
        User,
        models.CASCADE)
    name = models.CharField(
        _('name'),
        max_length=64,
        help_text=_('Repository display name'))
    slug = models.SlugField(
        _('slug'),
        max_length=32,
        help_text=_('Easy way to found and share repositories'))
    language = models.CharField(
        _('language'),
        choices=languages.LANGUAGE_CHOICES,
        max_length=2,
        help_text=_('Repository\'s examples language. The examples can be ' +
                    'translated to other languages.'))
    categories = models.ManyToManyField(
        RepositoryCategory,
        help_text=CATEGORIES_HELP_TEXT)
    description = models.TextField(
        _('description'),
        blank=True,
        help_text=DESCRIPTION_HELP_TEXT)
    is_private = models.BooleanField(
        _('private'),
        default=False,
        help_text=_('Your repository can be private, only you can see and' +
                    ' use, or can be public and all community can see and ' +
                    'use.'))
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True)

    @property
    def available_languages(self):
        examples = self.examples()
        examples_languages = examples.values_list(
            'repository_update__language',
            flat=True)
        translations_languages = examples.annotate(
            translations_count=models.Count('translations')).filter(
                translations_count__gt=0).values_list(
                    'translations__language',
                    flat=True)
        return list(set(
            [self.language] +
            list(examples_languages) +
            list(translations_languages)))

    @property
    def languages_status(self):
        return dict(
            map(
                lambda language: (
                    language,
                    self.language_status(language)),
                languages.SUPPORTED_LANGUAGES,
            ))

    def examples(self, language=None, deleted=True, queryset=None):
        if queryset is None:
            queryset = RepositoryExample.objects
        query = queryset.filter(
            repository_update__repository=self)
        if language:
            query = query.filter(
                repository_update__language=language)
        if deleted:
            return query.exclude(deleted_in__isnull=False)
        return query

    def language_status(self, language):
        is_base_language = self.language == language
        examples = self.examples(language)
        base_examples = self.examples(self.language)
        base_translations = RepositoryTranslatedExample.objects.filter(
            original_example__in=base_examples,
            language=language)

        examples_count = examples.count()
        base_examples_count = base_examples.count()
        base_translations_count = base_translations.count()
        base_translations_percentage = (
            base_translations_count / (
                base_examples_count if base_examples_count > 0 else 1)) * 100

        return {
            'is_base_language': is_base_language,
            'examples': {
                'count': examples_count,
                'entities': list(examples.values_list(
                    'entities__entity',
                    flat=True).distinct()),
            },
            'base_translations': {
                'count': base_translations_count,
                'percentage': base_translations_percentage,
            },
        }

    def current_update(self, language=None):
        language = language or self.language
        repository_update, created = self.updates.get_or_create(
            language=language,
            training_started_at=None)
        return repository_update

    def current_rasa_nlu_data(self, language=None):
        return self.current_update(language).rasa_nlu_data

    def last_trained_update(self, language=None):
        language = language or self.language
        return self.updates.filter(
            language=language,
            by__isnull=False).first()

    def get_user_authorization(self, user):
        if user.is_anonymous:
            return RepositoryAuthorization(repository=self)
        get, created = RepositoryAuthorization.objects.get_or_create(
            user=user,
            repository=self)

        return get


class RepositoryUpdate(models.Model):
    class Meta:
        verbose_name = _('repository update')
        verbose_name_plural = _('repository updates')
        ordering = ['-created_at']

    repository = models.ForeignKey(
        Repository,
        models.CASCADE,
        related_name='updates')
    language = models.CharField(
        _('language'),
        choices=languages.LANGUAGE_CHOICES,
        max_length=2)
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True)
    bot_data = models.TextField(
        _('bot data'),
        blank=True,
        editable=False)
    by = models.ForeignKey(
        User,
        models.CASCADE,
        blank=True,
        null=True)
    training_started_at = models.DateTimeField(
        _('training started at'),
        blank=True,
        null=True)
    trained_at = models.DateTimeField(
        _('trained at'),
        blank=True,
        null=True)

    @property
    def examples(self):
        examples = self.repository.examples(deleted=False).filter(
            models.Q(repository_update__language=self.language) |
            models.Q(translations__language=self.language))
        if self.training_started_at:
            t_started_at = self.training_started_at
            examples = examples.exclude(
                models.Q(repository_update__created_at__gt=t_started_at) |
                models.Q(deleted_in=self) |
                models.Q(deleted_in__training_started_at__lt=t_started_at))
        else:
            examples = examples.exclude(deleted_in=self)
        return examples

    @property
    def rasa_nlu_data(self):
        return {
            'common_examples': list(
                map(
                    lambda example: example.to_rasa_nlu_data(self.language),
                    filter(
                        lambda example: example.has_valid_entities(
                            self.language),
                        self.examples)))
        }

    def start_training(self, by):
        if self.trained_at:
            raise RepositoryUpdateAlreadyTrained()
        if self.training_started_at:
            raise RepositoryUpdateAlreadyStartedTraining()

        authorization = self.repository.get_user_authorization(by)
        if not authorization.can_write:
            raise TrainingNotAllowed()

        self.by = by
        self.training_started_at = timezone.now()
        self.save(
            update_fields=[
                'by',
                'training_started_at',
            ])

    def save_training(self, bot_data):
        if self.trained_at:
            raise RepositoryUpdateAlreadyTrained()

        self.trained_at = timezone.now()
        self.bot_data = base64.b64encode(bot_data).decode('utf8')
        self.save(
            update_fields=[
                'trained_at',
                'bot_data',
            ])

    def get_bot_data(self):
        return base64.b64decode(self.bot_data)


class RepositoryExample(models.Model):
    class Meta:
        verbose_name = _('repository example')
        verbose_name_plural = _('repository examples')
        ordering = ['-created_at']

    repository_update = models.ForeignKey(
        RepositoryUpdate,
        models.CASCADE,
        related_name='added',
        editable=False)
    deleted_in = models.ForeignKey(
        RepositoryUpdate,
        models.CASCADE,
        related_name='deleted',
        blank=True,
        null=True)
    text = models.TextField(
        _('text'),
        help_text=_('Example text'))
    intent = models.CharField(
        _('intent'),
        max_length=64,
        blank=True,
        help_text=_('Example intent reference'))
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True)

    @property
    def language(self):
        return self.repository_update.language

    def has_valid_entities(self, language=None):
        if not language or language == self.repository_update.language:
            return True
        return self.get_translation(language).has_valid_entities

    def get_translation(self, language):
        try:
            return self.translations.get(language=language)
        except RepositoryTranslatedExample.DoesNotExist:
            raise DoesNotHaveTranslation()

    def get_text(self, language=None):
        if not language or language == self.repository_update.language:
            return self.text
        return self.get_translation(language).text

    def get_entities(self, language):
        if not language or language == self.repository_update.language:
            return self.entities.all()
        return self.get_translation(language).entities.all()

    def to_rasa_nlu_data(self, language):
        return {
            'text': self.get_text(language),
            'intent': self.intent,
            'entities': [
                entity.to_rasa_nlu_data for entity in self.get_entities(
                    language)],
        }

    def delete(self):
        self.deleted_in = self.repository_update.repository.current_update(
            self.repository_update.language)
        self.save(update_fields=['deleted_in'])


class RepositoryTranslatedExample(models.Model):
    class Meta:
        verbose_name = _('repository translated example')
        verbose_name_plural = _('repository translated examples')
        unique_together = ['original_example', 'language']

    original_example = models.ForeignKey(
        RepositoryExample,
        models.CASCADE,
        related_name='translations',
        editable=False,
        help_text=_('Example object'))
    language = models.CharField(
        _('language'),
        choices=languages.LANGUAGE_CHOICES,
        max_length=2,
        help_text=_('Translation language'))
    text = models.TextField(
        _('text'),
        help_text=_('Translation text'))

    @classmethod
    def create_entitites_count_dict(cls, entities):
        return dict(
            list(
                map(
                    lambda x: (x.get('entity'), x.get('many'),),
                    entities.values('entity').annotate(
                        many=models.Count('entity')))))

    @property
    def has_valid_entities(self):
        original_entities = self.original_example.entities.all()
        my_entities = self.entities.all()
        if original_entities.count() != my_entities.count():
            return False
        original_entities_dict = RepositoryTranslatedExample \
            .create_entitites_count_dict(original_entities)
        my_entities_dict = RepositoryTranslatedExample \
            .create_entitites_count_dict(my_entities)
        if len(set(original_entities_dict) ^ set(my_entities_dict)) > 0:
            return False
        for key in original_entities_dict:
            if original_entities_dict.get(key) != my_entities_dict.get(key):
                return False
        return True


class EntityBase(models.Model):
    class Meta:
        verbose_name = _('repository example entity')
        verbose_name_plural = _('repository example entities')
        abstract = True

    start = models.PositiveIntegerField(
        _('start'),
        help_text=_('Start index of entity value in example text'))
    end = models.PositiveIntegerField(
        _('end'),
        help_text=_('End index of entity value in example text'))
    entity = models.CharField(
        _('entity'),
        max_length=64,
        help_text=_('Entity name'))
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True)

    @property
    def value(self):
        return self.get_example().text[self.start:self.end]

    @property
    def to_rasa_nlu_data(self):
        return {
            'start': self.start,
            'end': self.end,
            'value': self.value,
            'entity': self.entity,
        }

    def get_example(self):
        pass  # pragma: no cover


class RepositoryExampleEntity(EntityBase):
    repository_example = models.ForeignKey(
        RepositoryExample,
        models.CASCADE,
        related_name='entities',
        editable=False,
        help_text=_('Example object'))

    def get_example(self):
        return self.repository_example


class RepositoryTranslatedExampleEntity(EntityBase):
    repository_translated_example = models.ForeignKey(
        RepositoryTranslatedExample,
        models.CASCADE,
        related_name='entities',
        editable=False,
        help_text=_('Translated example object'))

    def get_example(self):
        return self.repository_translated_example


class RepositoryAuthorization(models.Model):
    class Meta:
        verbose_name = _('repository authorization')
        verbose_name_plural = _('repository authorizations')
        unique_together = ['user', 'repository']

    LEVEL_NOTHING = 0
    LEVEL_READER = 1
    LEVEL_ADMIN = 2

    uuid = models.UUIDField(
        _('UUID'),
        primary_key=True,
        default=uuid.uuid4,
        editable=False)
    user = models.ForeignKey(
        User,
        models.CASCADE)
    repository = models.ForeignKey(
        Repository,
        models.CASCADE)
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True)

    @property
    def level(self):
        try:
            user = self.user
        except User.DoesNotExist:
            user = None

        if user and self.repository.owner == user:
            return RepositoryAuthorization.LEVEL_ADMIN
        if self.repository.is_private:
            return RepositoryAuthorization.LEVEL_NOTHING
        return RepositoryAuthorization.LEVEL_READER

    @property
    def can_read(self):
        return self.level in [
            RepositoryAuthorization.LEVEL_READER,
            RepositoryAuthorization.LEVEL_ADMIN,
        ]

    @property
    def can_contribute(self):
        return self.level in [
            RepositoryAuthorization.LEVEL_ADMIN,
        ]

    @property
    def can_write(self):
        return self.level in [
            RepositoryAuthorization.LEVEL_ADMIN,
        ]

    @property
    def is_admin(self):
        return self.level == RepositoryAuthorization.LEVEL_ADMIN