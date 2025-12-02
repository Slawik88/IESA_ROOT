from django.db import models

class Partner(models.Model):
    """
    Модель для отображения партнеров ассоциации.
    """
    name = models.CharField(max_length=255, verbose_name='Название партнера')
    logo = models.ImageField(upload_to='partners/', verbose_name='Логотип')
    link = models.URLField(blank=True, verbose_name='Ссылка на сайт')
    description = models.TextField(blank=True, verbose_name='Описание')
    
    class Meta:
        verbose_name = 'Партнер'
        verbose_name_plural = 'Партнеры'
        
    def __str__(self):
        return self.name

class AssociationMember(models.Model):
    """
    Модель для отображения членов ассоциации (кроме президента).
    """
    name = models.CharField(max_length=255, verbose_name='Имя и Фамилия')
    photo = models.ImageField(upload_to='members/', verbose_name='Фото')
    position = models.CharField(max_length=255, verbose_name='Должность')
    description = models.TextField(verbose_name='Краткое описание/Биография')
    
    class Meta:
        verbose_name = 'Член ассоциации'
        verbose_name_plural = 'Члены ассоциации'
        
    def __str__(self):
        return self.name