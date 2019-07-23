from django.utils.translation import gettext as _
from rest_framework import serializers

from bothub.api.v1.serializers import \
    RepositoryTranslatedExampleEntitySeralizer
from bothub.api.v1.validators import CanContributeInRepositoryExampleValidator
from bothub.api.v2.example.serializers import RepositoryExampleEntitySerializer
from bothub.common.models import Repository
from bothub.common.models import RepositoryTranslatedExample
from bothub.common.models import RepositoryExample
from bothub.common.models import RepositoryVote
from bothub.common.models import RepositoryCategory
from bothub.common.models import RepositoryEntityLabel
from bothub.common.models import RepositoryAuthorization
from bothub.common.models import RequestRepositoryAuthorization
from bothub.common.languages import LANGUAGE_CHOICES
from ..request.serializers import RequestRepositoryAuthorizationSerializer
from ..fields import ModelMultipleChoiceField
from ..fields import TextField


class RepositoryCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RepositoryCategory
        fields = [
            'id',
            'name',
            'icon',
        ]
        ref_name = None


class RepositoryEntityLabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepositoryEntityLabel
        fields = [
            'repository',
            'value',
            'entities',
            'examples__count',
        ]
        ref_name = None

    entities = serializers.SerializerMethodField()
    examples__count = serializers.SerializerMethodField()

    def get_entities(self, obj):
        entities = obj.repository.other_entities \
            if obj.value == 'other' else obj.entities.all()
        return map(lambda e: e.value, entities)

    def get_examples__count(self, obj):
        if obj.value == 'other':
            return obj.repository.examples(
                exclude_deleted=True).filter(
                    entities__entity__in=obj.repository.other_entities) \
                    .count()
        return obj.examples().count()


class IntentSerializer(serializers.Serializer):
    value = serializers.CharField()
    examples__count = serializers.IntegerField()


class RepositoryAuthorizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepositoryAuthorization
        fields = [
            'uuid',
            'user',
            'user__nickname',
            'repository',
            'role',
            'level',
            'can_read',
            'can_contribute',
            'can_write',
            'is_admin',
            'created_at',
        ]
        read_only = [
            'user',
            'user__nickname',
            'repository',
            'role',
            'created_at',
        ]
        ref_name = None

    user__nickname = serializers.SlugRelatedField(
        source='user',
        slug_field='nickname',
        read_only=True)


class RepositorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Repository
        fields = [
            'uuid',
            'name',
            'slug',
            'description',
            'is_private',
            'available_languages',
            'entities',
            'entities_list',
            'labels_list',
            'ready_for_train',
            'created_at',
            'language',
            'owner',
            'owner__nickname',
            'categories',
            'categories_list',
            'intents',
            'intents_list',
            'labels',
            'other_label',
            'examples__count',
            'evaluate_languages_count',
            'absolute_url',
            'authorization',
            'ready_for_train',
            'requirements_to_train',
            'languages_ready_for_train',
            'request_authorization',
            'available_request_authorization',
            'languages_warnings',
            'algorithm',
            'use_language_model_featurizer',
            'use_competing_intents',
            'use_name_entities',
        ]
        read_only = [
            'uuid',
            'available_languages',
            'entities',
            'entities_list',
            'evaluate_languages_count',
            'labels_list',
            'ready_for_train',
            'created_at',
            'authorization',
        ]
        ref_name = None

    language = serializers.ChoiceField(
        LANGUAGE_CHOICES,
        label=Repository._meta.get_field('language').verbose_name)
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    owner__nickname = serializers.SlugRelatedField(
        source='owner',
        slug_field='nickname',
        read_only=True)
    intents = serializers.SerializerMethodField()
    intents_list = serializers.SerializerMethodField()
    categories = RepositoryCategorySerializer(
        many=True,
        read_only=True)
    categories_list = serializers.SlugRelatedField(
        source='categories',
        slug_field='name',
        many=True,
        read_only=True)
    labels = RepositoryEntityLabelSerializer(
        source='current_labels',
        many=True,
        read_only=True)
    other_label = serializers.SerializerMethodField()
    examples__count = serializers.SerializerMethodField()
    evaluate_languages_count = serializers.SerializerMethodField()
    absolute_url = serializers.SerializerMethodField()
    authorization = serializers.SerializerMethodField()
    request_authorization = serializers.SerializerMethodField()
    available_request_authorization = serializers.SerializerMethodField()
    entities = serializers.SerializerMethodField()

    def create(self, validated_data):
        validated_data.update({
            'owner': self.context['request'].user,
        })
        return super().create(validated_data)

    def get_entities(self, obj):
        return obj.current_entities.values('value', 'id').distinct()

    def get_intents(self, obj):
        return IntentSerializer(
            map(
                lambda intent: {
                    'value': intent,
                    'examples__count': obj.examples(
                        exclude_deleted=True).filter(
                            intent=intent).count(),
                },
                obj.intents),
            many=True).data

    def get_intents_list(self, obj):
        return obj.intents

    def get_other_label(self, obj):
        return RepositoryEntityLabelSerializer(
            RepositoryEntityLabel(
                repository=obj,
                value='other')).data

    def get_examples__count(self, obj):
        return obj.examples().count()

    def get_evaluate_languages_count(self, obj):
        return dict(map(
            lambda x: (x, obj.evaluations(language=x).count()
                       ), obj.available_languages
        ))

    def get_absolute_url(self, obj):
        return obj.get_absolute_url()

    def get_authorization(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        return RepositoryAuthorizationSerializer(
            obj.get_user_authorization(request.user)).data

    def get_request_authorization(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        try:
            request_authorization = RequestRepositoryAuthorization.objects.get(
                user=request.user,
                repository=obj)
            return RequestRepositoryAuthorizationSerializer(
                request_authorization).data
        except RequestRepositoryAuthorization.DoesNotExist:
            return None

    def get_available_request_authorization(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        authorization = obj.get_user_authorization(request.user)
        if authorization.role is not RepositoryAuthorization.ROLE_NOT_SETTED:
            return False
        if authorization.is_owner:
            return False
        try:
            RequestRepositoryAuthorization.objects.get(
                user=request.user,
                repository=obj)
            return False
        except RequestRepositoryAuthorization.DoesNotExist:
            return True


class ShortRepositorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Repository
        fields = [
            'uuid',
            'name',
            'slug',
            'description',
            'is_private',
            'categories',
            'categories_list',
            'language',
            'available_languages',
            'created_at',
            'owner',
            'owner__nickname',
            'absolute_url',
        ]
        read_only = fields
        ref_name = None

    categories = RepositoryCategorySerializer(
        many=True,
        read_only=True)
    categories_list = serializers.SlugRelatedField(
        source='categories',
        slug_field='name',
        many=True,
        read_only=True)
    owner__nickname = serializers.SlugRelatedField(
        source='owner',
        slug_field='nickname',
        read_only=True)
    absolute_url = serializers.SerializerMethodField()

    def get_absolute_url(self, obj):
        return obj.get_absolute_url()


class RepositoryVotesSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepositoryVote
        fields = [
            'user',
            'repository',
            'created',
        ]

        read_only_fields = [
            'user',
            'created_at',
        ]
        ref_name = None

    def create(self, validated_data):
        user = self.context.get('request').user
        repository = validated_data.pop('repository')
        vote, created = RepositoryVote.objects.get_or_create(
            repository=repository,
            user=user
        )
        return vote


class RepositoryContributionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepositoryAuthorization
        fields = [
            'user',
            'repository',
            'role',
            'created_at',
        ]

        read_only_fields = [
            'user',
            'role',
            'created_at',
        ]
        ref_name = None


class RepositoryCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RepositoryCategory
        fields = [
            'id',
            'name',
            'icon',
        ]
        ref_name = None


class NewRepositorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Repository
        fields = [
            'uuid',
            'owner',
            'name',
            'slug',
            'language',
            'algorithm',
            'use_competing_intents',
            'use_name_entities',
            'categories',
            'description',
            'is_private',
        ]
        ref_name = None

    uuid = serializers.ReadOnlyField(
        style={'show': False})
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    language = serializers.ChoiceField(
        LANGUAGE_CHOICES,
        label=_('Language'))
    categories = ModelMultipleChoiceField(
        child_relation=serializers.PrimaryKeyRelatedField(
            queryset=RepositoryCategory.objects.all()),
        allow_empty=False,
        help_text=Repository.CATEGORIES_HELP_TEXT)
    description = TextField(
        allow_blank=True,
        help_text=Repository.DESCRIPTION_HELP_TEXT)


class RepositoryTranslatedExampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepositoryTranslatedExample
        fields = [
            'id',
            'original_example',
            'from_language',
            'language',
            'text',
            'has_valid_entities',
            'entities',
            'created_at',
        ]
        ref_name = None

    original_example = serializers.PrimaryKeyRelatedField(
        queryset=RepositoryExample.objects,
        validators=[
            CanContributeInRepositoryExampleValidator(),
        ],
        help_text=_('Example\'s ID'))
    from_language = serializers.SerializerMethodField()
    has_valid_entities = serializers.SerializerMethodField()
    entities = RepositoryTranslatedExampleEntitySeralizer(
        many=True,
        read_only=True)

    def get_from_language(self, obj):
        return obj.original_example.repository_update.language

    def get_has_valid_entities(self, obj):
        return obj.has_valid_entities


class RepositoryExampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepositoryExample
        fields = [
            'id',
            'repository_update',
            'deleted_in',
            'text',
            'intent',
            'language',
            'created_at',
            'entities',
            'translations',
        ]
        read_only_fields = [
            'repository_update',
            'deleted_in',
        ]
        ref_name = None

    entities = RepositoryExampleEntitySerializer(
        many=True,
        read_only=True)
    translations = RepositoryTranslatedExampleSerializer(
        many=True,
        read_only=True)
    language = serializers.SerializerMethodField()

    def get_language(self, obj):
        return obj.language
