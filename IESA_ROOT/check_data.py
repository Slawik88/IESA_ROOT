from blog.models import Post
from users.models import User

posts = Post.objects.filter(status='published').count()
users = User.objects.count()

print(f'Posts (published): {posts}')
print(f'Users: {users}')

if posts > 0:
    sample = Post.objects.filter(status='published').first()
    print(f'Sample post: {sample.title}')
else:
    print('No published posts found')
