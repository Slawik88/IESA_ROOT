def global_search(request):
    """
    Global HTMX search endpoint for posts, users, events, partners
    """
    from django.db.models import Q, Value, Case, When, IntegerField, Count
    from core.models import Partner
    from users.models import User
    
    q = request.GET.get('q', '').strip()
    normalized_q = normalize_search_query(q)
    results = {
        'users': [],
        'posts': [],
        'events': [],
        'partners': []
    }
    
    if normalized_q:
        # Search users
        users = User.objects.filter(
            Q(username__icontains=normalized_q) |
            Q(first_name__icontains=normalized_q) |
            Q(last_name__icontains=normalized_q) |
            Q(email__icontains=normalized_q)
        ).order_by('-is_verified', 'username')[:8]
        results['users'] = list(users)
        
        # Search posts
        posts = Post.objects.filter(
            Q(title__icontains=normalized_q) |
            Q(text__icontains=normalized_q)
        ).annotate(
            relevance=Case(
                When(title__icontains=normalized_q, then=Value(10)),
                default=Value(1),
                output_field=IntegerField()
            )
        ).order_by('-relevance', '-created_at')[:6]
        results['posts'] = list(posts)
        
        # Search events
        events = Event.objects.filter(
            Q(title__icontains=normalized_q) |
            Q(description__icontains=normalized_q)
        ).annotate(
            relevance=Case(
                When(title__icontains=normalized_q, then=Value(10)),
                default=Value(1),
                output_field=IntegerField()
            )
        ).order_by('-relevance', '-date')[:6]
        results['events'] = list(events)
        
        # Search partners
        partners = Partner.objects.filter(
            Q(name__icontains=normalized_q) |
            Q(description__icontains=normalized_q)
        ).annotate(
            relevance=Case(
                When(name__icontains=normalized_q, then=Value(10)),
                default=Value(1),
                output_field=IntegerField()
            )
        ).order_by('-relevance', 'name')[:6]
        results['partners'] = list(partners)
    
    context = {'query': q, 'results': results}
    return render(request, 'blog/htmx/global_search_results.html', context)
