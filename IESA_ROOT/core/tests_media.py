"""Production image conversion is compatible with the patched Pillow runtime."""
from io import BytesIO

from django.test import SimpleTestCase
from PIL import Image

from IESA_ROOT.storage import _is_optimisable, _to_webp


class MediaConversionTests(SimpleTestCase):
    def image_file(self, mode='RGB', size=(1200, 600), format='PNG', **options):
        file = BytesIO()
        with Image.new(mode, size) as image:
            image.save(file, format=format, **options)
        file.seek(0)
        return file

    def test_avatar_and_artwork_have_separate_resize_budgets(self):
        for path, size in (('avatars/user.png', (300, 150)), ('blog/post.png', (800, 400))):
            with self.subTest(path=path):
                with self.image_file() as file:
                    self.assertTrue(_is_optimisable(file))
                    with Image.open(BytesIO(_to_webp(file, path))) as result:
                        self.assertEqual(result.format, 'WEBP')
                        self.assertEqual(result.size, size)

    def test_transparent_png_preserves_alpha(self):
        with self.image_file(mode='RGBA', size=(20, 20)) as file:
            with Image.open(BytesIO(_to_webp(file, 'avatars/transparent.png'))) as result:
                self.assertEqual(result.mode, 'RGBA')
                self.assertEqual(result.getpixel((0, 0))[3], 0)

    def test_exif_orientation_is_applied_and_metadata_is_removed(self):
        exif = Image.Exif()
        exif[274] = 6  # Rotate 90 degrees clockwise.
        exif[315] = 'Private author metadata'
        with self.image_file(size=(40, 20), format='JPEG', exif=exif) as file:
            with Image.open(BytesIO(_to_webp(file, 'blog/oriented.jpg'))) as result:
                self.assertEqual(result.size, (20, 40))
                self.assertFalse(result.getexif())

    def test_non_image_is_not_treated_as_optimisable(self):
        file = BytesIO(b'%PDF-1.4 not an image')
        self.assertFalse(_is_optimisable(file))
        self.assertEqual(file.tell(), 0)
