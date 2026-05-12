"""User search view."""
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render
from django_ratelimit.decorators import ratelimit

from ..models import User
from ..search_utils import highlight_text, normalize_search_query


@ratelimit(key='ip', rate='30/m', method='GET', block=True)
def users_search(request):
    q = request.GET.get('q', '').strip()
    page = request.GET.get('page', 1)
    normalized_q = normalize_search_query(q)
    highlighted_results = []
    paginator = Paginator([], 20)
    page_obj = paginator.get_page(1)

    if normalized_q and len(normalized_q) >= 2:
        results = User.objects.search(normalized_q).order_by(
            '-is_verified', 'username'
        ).values_list('id', 'username', 'first_name', 'last_name', 'email', 'permanent_id', flat=False)
        paginator = Paginator(results, 20)
        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        user_ids = [r[0] for r in page_obj.object_list]
        for user in User.objects.filter(id__in=user_ids).order_by('-is_verified', 'username'):
            highlighted_results.append({
                'user': user,
                'username_html':    highlight_text(user.username, normalized_q),
                'first_name_html':  highlight_text(user.first_name, normalized_q),
                'last_name_html':   highlight_text(user.last_name, normalized_q),
                'email_html':       highlight_text(user.email, normalized_q),
                'permanent_id_html': highlight_text(str(user.permanent_id), normalized_q),
            })
        page_obj.object_list = highlighted_results

    return render(request, 'users/search_results.html', {
        'results': highlighted_results,
        'page_obj': page_obj,
        'query': q,
        'is_paginated': page_obj.has_other_pages() if page_obj else False,
    })
