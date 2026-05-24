"""User search view."""
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render
from django_ratelimit.decorators import ratelimit

from ..models import User
from ..search_utils import highlight_text, normalize_search_query


@ratelimit(key='ip', rate='30/m', method='GET', block=True)
def users_search(request):
    """audit v5: расширен фильтрами по роли + сортировкой.

    Query params:
      - q: поисковая строка
      - role: 'all' | 'partner' | 'staff' | 'member' | 'president' | 'verified'
      - sort: 'relevance' | 'newest' | 'oldest' | 'az' | 'za'
    """
    q = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', 'all').strip().lower()
    sort_by = request.GET.get('sort', 'relevance').strip().lower()
    page = request.GET.get('page', 1)
    normalized_q = normalize_search_query(q)
    highlighted_results = []
    paginator = Paginator([], 20)
    page_obj = paginator.get_page(1)

    # Базовый queryset — с фильтром q или все юзеры если задан role/sort без q
    has_search = normalized_q and len(normalized_q) >= 2
    has_filter = role_filter not in ('all', '')
    if has_search:
        qs = User.objects.search(normalized_q)
    elif has_filter:
        qs = User.objects.all()
    else:
        qs = None

    if qs is not None:
        # Фильтр по роли
        if role_filter == 'partner':
            qs = qs.filter(is_partner=True)
        elif role_filter == 'staff':
            qs = qs.filter(is_staff=True)
        elif role_filter == 'member':
            qs = qs.filter(membership_status='active', is_partner=False, is_staff=False)
        elif role_filter == 'president':
            qs = qs.filter(is_president=True)
        elif role_filter == 'verified':
            qs = qs.filter(is_verified=True)

        # Сортировка
        if sort_by == 'newest':
            qs = qs.order_by('-date_joined')
        elif sort_by == 'oldest':
            qs = qs.order_by('date_joined')
        elif sort_by == 'az':
            qs = qs.order_by('username')
        elif sort_by == 'za':
            qs = qs.order_by('-username')
        else:  # relevance (default)
            qs = qs.order_by('-is_verified', 'username')

        results = qs.values_list('id', 'username', 'first_name', 'last_name', 'email', 'permanent_id', flat=False)
        paginator = Paginator(results, 20)
        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        user_ids = [r[0] for r in page_obj.object_list]
        # Preserve order from page_obj
        order_map = {uid: idx for idx, uid in enumerate(user_ids)}
        users = list(User.objects.filter(id__in=user_ids))
        users.sort(key=lambda u: order_map.get(u.id, 999))

        for user in users:
            highlighted_results.append({
                'user': user,
                'username_html':    highlight_text(user.username, normalized_q) if normalized_q else user.username,
                'first_name_html':  highlight_text(user.first_name, normalized_q) if normalized_q else user.first_name,
                'last_name_html':   highlight_text(user.last_name, normalized_q) if normalized_q else user.last_name,
                'email_html':       highlight_text(user.email, normalized_q) if normalized_q else user.email,
                'permanent_id_html': highlight_text(str(user.permanent_id), normalized_q) if normalized_q else str(user.permanent_id),
            })
        page_obj.object_list = highlighted_results

    from django.utils.translation import gettext as _gt
    return render(request, 'users/search_results.html', {
        'results': highlighted_results,
        'page_obj': page_obj,
        'query': q,
        'role_filter': role_filter,
        'sort_by': sort_by,
        'role_choices_display': [
            ('all',       _gt('All')),
            ('partner',   _gt('Partners')),
            ('staff',     _gt('Staff')),
            ('member',    _gt('Members')),
            ('president', _gt('President')),
            ('verified',  _gt('Verified')),
        ],
        'is_paginated': page_obj.has_other_pages() if page_obj else False,
    })
