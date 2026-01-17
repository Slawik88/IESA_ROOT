"""User app constants and configuration data."""

# Activity level definitions
# FIX: Extracted from views.py to make it reusable and testable
ACTIVITY_LEVELS = [
    {
        'name': 'Beginner',
        'icon': 'leaf',
        'color': 'secondary',
        'min_points': 0,
        'max_points': 50,
        'description': 'Just starting your journey in the IESA community',
        'tips': [
            'Create your first blog post (10 points)',
            'Leave comments on other posts (1 point each)',
            'Engage with the community',
        ]
    },
    {
        'name': 'Intermediate',
        'icon': 'fire',
        'color': 'success',
        'min_points': 50,
        'max_points': 200,
        'description': 'You\'re becoming an active member',
        'tips': [
            'Publish 5-10 quality posts (10 points each)',
            'Receive 50+ likes on your posts (2 points each)',
            'Participate in discussions',
        ]
    },
    {
        'name': 'Advanced',
        'icon': 'rocket',
        'color': 'info',
        'min_points': 200,
        'max_points': 500,
        'description': 'You\'re a valuable contributor',
        'tips': [
            'Publish 15-25 popular posts',
            'Accumulate 100+ total likes',
            'Build a strong reputation',
        ]
    },
    {
        'name': 'Expert',
        'icon': 'star',
        'color': 'warning',
        'min_points': 500,
        'max_points': 1000,
        'description': 'You\'re a recognized authority',
        'tips': [
            'Publish 50+ high-quality posts',
            'Achieve 300+ total likes',
            'Mentor other members',
        ]
    },
    {
        'name': 'Legend',
        'icon': 'crown',
        'color': 'danger',
        'min_points': 1000,
        'max_points': 'Unlimited',
        'description': 'You\'re a pillar of the IESA community',
        'tips': [
            'Maintain extraordinary engagement',
            'Lead by example',
            'Shape the future of IESA',
        ]
    },
]

# Points breakdown for different actions
POINTS_BREAKDOWN = {
    'post': 10,
    'like': 2,
    'comment': 1,
}
