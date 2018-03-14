from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins
from rest_framework import permissions
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework.exceptions import APIException
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import PermissionDenied
from django.utils.translation import gettext as _
from django.db.models import Count
from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters import rest_framework as filters

from bothub.common.models import Repository
from bothub.common.models import RepositoryExample
from bothub.common.models import RepositoryExampleEntity
from bothub.common.models import RepositoryTranslatedExample
from bothub.common.models import RepositoryTranslatedExampleEntity
from bothub.authentication.models import User

from .serializers import RepositorySerializer
from .serializers import RepositoryExampleSerializer
from .serializers import RepositoryExampleEntitySerializer
from .serializers import RepositoryAuthorizationSerializer
from .serializers import RepositoryTranslatedExampleSerializer
from .serializers import RepositoryTranslatedExampleEntitySeralizer
from .serializers import RegisterUserSerializer
from .serializers import UserSerializer


# Permisions

READ_METHODS = permissions.SAFE_METHODS
WRITE_METHODS = ['POST', 'PUT', 'PATCH']
ADMIN_METHODS = ['DELETE']


class RepositoryPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        authorization = obj.get_user_authorization(request.user)
        if request.method in READ_METHODS:
            return authorization.can_read
        if request.method in WRITE_METHODS:
            return authorization.can_write
        return authorization.is_admin


class RepositoryExamplePermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        authorization = obj.repository_update.repository \
            .get_user_authorization(request.user)
        if request.method in READ_METHODS:
            return authorization.can_read
        return authorization.can_contribute


class RepositoryExampleEntityPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        authorization = obj.repository_example.repository_update.repository \
            .get_user_authorization(request.user)
        if request.method in READ_METHODS:
            return authorization.can_read
        return authorization.can_contribute


class RepositoryTranslatedExamplePermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        repository = obj.original_example.repository_update.repository
        authorization = repository.get_user_authorization(request.user)
        if request.method in READ_METHODS:
            return authorization.can_read
        return authorization.can_contribute


class RepositoryTranslatedExampleEntityPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        repository = obj.repository_translated_example.original_example \
            .repository_update.repository
        authorization = repository.get_user_authorization(request.user)
        if request.method in READ_METHODS:
            return authorization.can_read
        return authorization.can_contribute


class UserPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user == obj


# Filters

class ExamplesFilter(filters.FilterSet):
    class Meta:
        model = RepositoryExample
        fields = [
            'text',
            'language',
        ]

    repository_uuid = filters.CharFilter(
        name='repository_uuid',
        method='filter_repository_uuid',
        required=True,
        help_text=_('Repository\'s UUID'))
    language = filters.CharFilter(
        name='language',
        method='filter_language',
        help_text='Filter by language, default is repository base language')
    has_translation = filters.BooleanFilter(
        name='has_translation',
        method='filter_has_translation',
        help_text=_('Filter for examples with or without translation'))

    def filter_repository_uuid(self, queryset, name, value):
        request = self.request
        try:
            repository = Repository.objects.get(uuid=value)
            authorization = repository.get_user_authorization(request.user)
            if not authorization.can_read:
                raise PermissionDenied()
            return queryset.filter(
                repository_update__repository=repository)
        except Repository.DoesNotExist:
            raise NotFound(
                _('Repository {} does not exist').format(value))
        except DjangoValidationError:
            raise NotFound(_('Invalid repository_uuid'))

    def filter_language(self, queryset, name, value):
        return queryset.filter(repository_update__language=value)

    def filter_has_translation(self, queryset, name, value):
        annotated_queryset = queryset.annotate(
            translation_count=Count('translations'))
        if value:
            return annotated_queryset.filter(
                translation_count__gt=0)
        else:
            return annotated_queryset.filter(
                translation_count=0)


# ViewSets

class NewRepositoryViewSet(
        mixins.CreateModelMixin,
        GenericViewSet):
    """
    Create a new Repository, add examples and train a bot.
    """
    queryset = Repository.objects
    serializer_class = RepositorySerializer
    permission_classes = [permissions.IsAuthenticated]


class MyRepositoriesViewSet(
        mixins.ListModelMixin,
        GenericViewSet):
    """
    List all user's repositories
    """
    queryset = Repository.objects
    serializer_class = RepositorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self, *args, **kwargs):
        return self.queryset.filter(owner=self.request.user)


class RepositoryViewSet(
        mixins.RetrieveModelMixin,
        mixins.UpdateModelMixin,
        mixins.DestroyModelMixin,
        GenericViewSet):
    """
    Manager repository.

    retrieve:
    Get repository data.

    update:
    Update your repository.

    partial_update:
    Update, partially, your repository.

    delete:
    Delete your repository.
    """
    queryset = Repository.objects
    serializer_class = RepositorySerializer
    permission_classes = [
        permissions.IsAuthenticated,
        RepositoryPermission,
    ]

    @detail_route(
        methods=['GET'],
        url_name='repository-languages-status')
    def languagesstatus(self, request, **kwargs):
        """
        Get current language status.
        """
        repository = self.get_object()
        return Response({
            'languages_status': repository.languages_status,
        })

    @detail_route(
        methods=['GET'],
        url_name='repository-authorization')
    def authorization(self, request, **kwargs):
        """
        Get authorization to use in Bothub Natural Language Processing service.
        In Bothub NLP you can train the repository's bot and get interpreted
        messages.
        """
        repository = self.get_object()
        user_authorization = repository.get_user_authorization(request.user)
        serializer = RepositoryAuthorizationSerializer(user_authorization)
        return Response(serializer.data)


class NewRepositoryExampleViewSet(
        mixins.CreateModelMixin,
        GenericViewSet):
    """
    Create new repository example.
    """
    queryset = RepositoryExample.objects
    serializer_class = RepositoryExampleSerializer
    permission_classes = [permissions.IsAuthenticated]


class RepositoryExampleViewSet(
        mixins.RetrieveModelMixin,
        mixins.DestroyModelMixin,
        GenericViewSet):
    """
    Manager repository example.

    retrieve:
    Get repository example data.

    delete:
    Delete repository example.
    """
    queryset = RepositoryExample.objects
    serializer_class = RepositoryExampleSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        RepositoryExamplePermission,
    ]

    def perform_destroy(self, obj):
        if obj.deleted_in:
            raise APIException(_('Example already deleted'))
        obj.delete()


class NewRepositoryExampleEntityViewSet(
        mixins.CreateModelMixin,
        GenericViewSet):
    """
    Create new example entity.
    """
    queryset = RepositoryExampleEntity.objects
    serializer_class = RepositoryExampleEntitySerializer
    permission_classes = [permissions.IsAuthenticated]


class RepositoryExampleEntityViewSet(
        mixins.RetrieveModelMixin,
        mixins.DestroyModelMixin,
        GenericViewSet):
    """
    Manager example entity.

    retrieve:
    Get example entity data.

    delete:
    Delete example entity.
    """
    queryset = RepositoryExampleEntity.objects
    serializer_class = RepositoryExampleEntitySerializer
    permission_classes = [
        permissions.IsAuthenticated,
        RepositoryExampleEntityPermission,
    ]


class NewRepositoryTranslatedExampleViewSet(
        mixins.CreateModelMixin,
        GenericViewSet):
    queryset = RepositoryTranslatedExample.objects
    serializer_class = RepositoryTranslatedExampleSerializer
    permission_classes = [permissions.IsAuthenticated]


class RepositoryTranslatedExampleViewSet(
        mixins.RetrieveModelMixin,
        mixins.UpdateModelMixin,
        mixins.DestroyModelMixin,
        GenericViewSet):
    queryset = RepositoryTranslatedExample.objects
    serializer_class = RepositoryTranslatedExampleSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        RepositoryTranslatedExamplePermission,
    ]


class NewRepositoryTranslatedExampleEntityViewSet(
        mixins.CreateModelMixin,
        GenericViewSet):
    queryset = RepositoryTranslatedExampleEntity.objects
    serializer_class = RepositoryTranslatedExampleEntitySeralizer
    permission_classes = [permissions.IsAuthenticated]


class RepositoryTranslatedExampleEntityViewSet(
        mixins.RetrieveModelMixin,
        mixins.DestroyModelMixin,
        GenericViewSet):
    queryset = RepositoryTranslatedExampleEntity.objects
    serializer_class = RepositoryTranslatedExampleEntitySeralizer
    permission_classes = [
        permissions.IsAuthenticated,
        RepositoryTranslatedExampleEntityPermission,
    ]


class RepositoryExamplesViewSet(
        mixins.ListModelMixin,
        GenericViewSet):
    queryset = RepositoryExample.objects
    serializer_class = RepositoryExampleSerializer
    filter_class = ExamplesFilter
    permission_classes = [
        permissions.IsAuthenticated,
    ]


class RegisterUserViewSet(
        mixins.CreateModelMixin,
        GenericViewSet):
    queryset = User.objects
    serializer_class = RegisterUserSerializer


class UserViewSet(
        mixins.RetrieveModelMixin,
        mixins.UpdateModelMixin,
        GenericViewSet):
    queryset = User.objects
    serializer_class = UserSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        UserPermission,
    ]
