"""
Image optimization specifications for imagekit.
Automatically creates thumbnails and optimized versions of uploaded images.
"""
from imagekit import ImageSpec, register
from imagekit.processors import ResizeToFill, ResizeToFit
from pilkit.processors import Thumbnail


class AvatarThumbnail(ImageSpec):
    """Small avatar thumbnail (150x150px)"""
    processors = [ResizeToFill(150, 150)]
    format = 'JPEG'
    options = {'quality': 85}


class BlogPreviewThumbnail(ImageSpec):
    """Blog post preview image (600x400px)"""
    processors = [ResizeToFill(600, 400)]
    format = 'JPEG'
    options = {'quality': 85}


class GalleryThumbnail(ImageSpec):
    """Gallery photo thumbnail (400x300px)"""
    processors = [ResizeToFill(400, 300)]
    format = 'JPEG'
    options = {'quality': 80}


class ProductImage(ImageSpec):
    """Product image optimized (800x800px max, maintains aspect ratio)"""
    processors = [ResizeToFit(800, 800)]
    format = 'JPEG'
    options = {'quality': 90}


# Register specs
register.generator('avatar_thumbnail', AvatarThumbnail)
register.generator('blog_preview_thumbnail', BlogPreviewThumbnail)
register.generator('gallery_thumbnail', GalleryThumbnail)
register.generator('product_image', ProductImage)
