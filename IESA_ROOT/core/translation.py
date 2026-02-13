from modeltranslation.translator import register, TranslationOptions
from .models import President, Partner, AssociationMember, CoreProduct, MemberBenefit


@register(President)
class PresidentTranslationOptions(TranslationOptions):
    fields = ('position', 'description')


@register(Partner)
class PartnerTranslationOptions(TranslationOptions):
    fields = ('description',)


@register(AssociationMember)
class AssociationMemberTranslationOptions(TranslationOptions):
    fields = ('position', 'description')


@register(CoreProduct)
class CoreProductTranslationOptions(TranslationOptions):
    fields = (
        'title', 
        'description', 
        'duration', 
        'location', 
        'features', 
        'price_info'
    )


@register(MemberBenefit)
class MemberBenefitTranslationOptions(TranslationOptions):
    fields = ('title', 'description', 'discount_info', 'partner_info', 'terms')
