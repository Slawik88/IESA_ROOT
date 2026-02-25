# Generated manually 2026-02-25 — seed real IESA member benefits
from django.db import migrations


BENEFITS = [
    {
        'title':          'Discounts on all association events',
        'title_en':       'Discounts on all association events',
        'title_uk':       'Знижки на всі заходи асоціації',
        'title_fr':       'Réductions sur tous les événements de l\'association',
        'title_de':       'Rabatte auf alle Vereinsveranstaltungen',
        'category':       'events',
        'description':    (
            'Members receive exclusive discounts when registering for any IESA event: '
            'extreme camps, yachting expeditions, competitions, and corporate adventures.'
        ),
        'description_en': (
            'Members receive exclusive discounts when registering for any IESA event: '
            'extreme camps, yachting expeditions, competitions, and corporate adventures.'
        ),
        'description_uk': (
            'Члени асоціації отримують ексклюзивні знижки на участь у всіх заходах IESA: '
            'екстремальні табори, яхтинг, змагання та корпоративні пригоди.'
        ),
        'description_fr': (
            'Les membres bénéficient de réductions exclusives pour tous les événements IESA : '
            'camps extrêmes, expéditions en yacht, compétitions et aventures d\'entreprise.'
        ),
        'description_de': (
            'Mitglieder erhalten exklusive Rabatte bei der Anmeldung für alle IESA-Veranstaltungen: '
            'Extremcamps, Segelexpeditionen, Wettkämpfe und Unternehmensabenteuer.'
        ),
        'discount_info':    'Special member pricing',
        'discount_info_en': 'Special member pricing',
        'discount_info_uk': 'Спеціальні ціни для членів',
        'discount_info_fr': 'Tarifs spéciaux membres',
        'discount_info_de': 'Sondertarife für Mitglieder',
        'icon':  'fas fa-ticket-alt',
        'color': 'primary',
        'partner_info':    'IESA Events',
        'partner_info_en': 'IESA Events',
        'partner_info_uk': 'Заходи IESA',
        'partner_info_fr': 'Événements IESA',
        'partner_info_de': 'IESA-Veranstaltungen',
        'terms':    'Discounts are applied automatically when booking through your personal cabinet.',
        'terms_en': 'Discounts are applied automatically when booking through your personal cabinet.',
        'terms_uk': 'Знижки застосовуються автоматично при реєстрації через особистий кабінет.',
        'terms_fr': 'Les réductions s\'appliquent automatiquement lors de l\'inscription via votre espace personnel.',
        'terms_de': 'Rabatte werden automatisch bei der Buchung über Ihr persönliches Konto angewendet.',
        'is_active': True,
        'order': 1,
    },
    {
        'title':          'Flexible insurance at competitive rates',
        'title_en':       'Flexible insurance at competitive rates',
        'title_uk':       'Гнучке страхування за вигідними тарифами',
        'title_fr':       'Assurance flexible à des tarifs avantageux',
        'title_de':       'Flexible Versicherung zu attraktiven Tarifen',
        'category':       'services',
        'description':    (
            'Access various types of insurance through IESA partner companies at preferential rates. '
            'Every insurance policy earns you bonus points that accumulate in your account.'
        ),
        'description_en': (
            'Access various types of insurance through IESA partner companies at preferential rates. '
            'Every insurance policy earns you bonus points that accumulate in your account.'
        ),
        'description_uk': (
            'Оформлення різних видів страхування через партнерів IESA за пільговими тарифами. '
            'За кожен страховий поліс нараховуються бонусні бали, що накопичуються на рахунку.'
        ),
        'description_fr': (
            'Souscrivez à différents types d\'assurances via les partenaires IESA à des tarifs préférentiels. '
            'Chaque police d\'assurance vous rapporte des points bonus qui s\'accumulent sur votre compte.'
        ),
        'description_de': (
            'Schließen Sie über IESA-Partnerunternehmen verschiedene Versicherungen zu Vorzugspreisen ab. '
            'Für jede Versicherungspolice erhalten Sie Bonuspunkte, die sich auf Ihrem Konto ansammeln.'
        ),
        'discount_info':    'Preferential rates + bonus points accrual',
        'discount_info_en': 'Preferential rates + bonus points accrual',
        'discount_info_uk': 'Пільгові тарифи + нарахування бонусних балів',
        'discount_info_fr': 'Tarifs préférentiels + accumulation de points bonus',
        'discount_info_de': 'Vorzugstarife + Bonuspunkte-Ansammlung',
        'icon':  'fas fa-shield-alt',
        'color': 'success',
        'partner_info':    'IESA Insurance Partners',
        'partner_info_en': 'IESA Insurance Partners',
        'partner_info_uk': 'Страхові партнери IESA',
        'partner_info_fr': 'Partenaires d\'assurance IESA',
        'partner_info_de': 'IESA-Versicherungspartner',
        'terms':    'Bonus points are credited after the insurance policy is issued.',
        'terms_en': 'Bonus points are credited after the insurance policy is issued.',
        'terms_uk': 'Бонусні бали нараховуються після оформлення страхового полісу.',
        'terms_fr': 'Les points bonus sont crédités après l\'émission de la police d\'assurance.',
        'terms_de': 'Bonuspunkte werden nach Ausstellung des Versicherungsscheins gutgeschrieben.',
        'is_active': True,
        'order': 2,
    },
    {
        'title':          'Pay for partner services with bonus points',
        'title_en':       'Pay for partner services with bonus points',
        'title_uk':       'Оплата послуг партнерів бонусними балами',
        'title_fr':       'Payer les services partenaires avec des points bonus',
        'title_de':       'Partnerleistungen mit Bonuspunkten bezahlen',
        'category':       'services',
        'description':    (
            'Use your accumulated bonus points to pay for services offered by other association members and official IESA partners. '
            'Points can cover the full cost of a service.'
        ),
        'description_en': (
            'Use your accumulated bonus points to pay for services offered by other association members and official IESA partners. '
            'Points can cover the full cost of a service.'
        ),
        'description_uk': (
            'Використовуйте накопичені бонусні бали для оплати послуг інших членів асоціації та офіційних партнерів IESA. '
            'Балами можна оплатити до 100% вартості послуги.'
        ),
        'description_fr': (
            'Utilisez vos points bonus accumulés pour payer les services des autres membres de l\'association et des partenaires officiels IESA. '
            'Les points peuvent couvrir la totalité du coût d\'un service.'
        ),
        'description_de': (
            'Verwenden Sie Ihre angesammelten Bonuspunkte, um Dienstleistungen anderer Vereinsmitglieder und offizieller IESA-Partner zu bezahlen. '
            'Punkte können die vollen Kosten einer Dienstleistung abdecken.'
        ),
        'discount_info':    'Up to 100% payment with bonus points',
        'discount_info_en': 'Up to 100% payment with bonus points',
        'discount_info_uk': 'Оплата до 100% бонусними балами',
        'discount_info_fr': 'Jusqu\'à 100% de paiement avec des points bonus',
        'discount_info_de': 'Bis zu 100% Bezahlung mit Bonuspunkten',
        'icon':  'fas fa-coins',
        'color': 'warning',
        'partner_info':    'All official IESA partners',
        'partner_info_en': 'All official IESA partners',
        'partner_info_uk': 'Усі офіційні партнери IESA',
        'partner_info_fr': 'Tous les partenaires officiels IESA',
        'partner_info_de': 'Alle offiziellen IESA-Partner',
        'terms':    'Points are accepted by all official IESA partners. Visit the partner dashboard to log a visit.',
        'terms_en': 'Points are accepted by all official IESA partners. Visit the partner dashboard to log a visit.',
        'terms_uk': 'Бали приймаються у всіх офіційних партнерів IESA.',
        'terms_fr': 'Les points sont acceptés par tous les partenaires officiels IESA.',
        'terms_de': 'Punkte werden von allen offiziellen IESA-Partnern akzeptiert.',
        'is_active': True,
        'order': 3,
    },
    {
        'title':          'Advertising presentations for active members',
        'title_en':       'Advertising presentations for active members',
        'title_uk':       'Рекламні презентації для активних членів',
        'title_fr':       'Présentations publicitaires pour les membres actifs',
        'title_de':       'Werbepräsentationen für aktive Mitglieder',
        'category':       'advertising',
        'description':    (
            'Active association members can publish promotional presentations about their business, '
            'services, or activities directly on the IESA website — reaching the entire community.'
        ),
        'description_en': (
            'Active association members can publish promotional presentations about their business, '
            'services, or activities directly on the IESA website — reaching the entire community.'
        ),
        'description_uk': (
            'Активні члени асоціації можуть розміщувати рекламні презентації про свою діяльність, '
            'послуги або бізнес безпосередньо на сайті IESA — охоплюючи всю спільноту.'
        ),
        'description_fr': (
            'Les membres actifs de l\'association peuvent publier des présentations promotionnelles sur leur activité, '
            'leurs services ou leur entreprise directement sur le site IESA — atteignant toute la communauté.'
        ),
        'description_de': (
            'Aktive Vereinsmitglieder können Werbepräsentationen über ihr Unternehmen, '
            'ihre Dienstleistungen oder Aktivitäten direkt auf der IESA-Website veröffentlichen — und die gesamte Gemeinschaft erreichen.'
        ),
        'discount_info':    'Free for active members',
        'discount_info_en': 'Free for active members',
        'discount_info_uk': 'Безкоштовно для активних членів',
        'discount_info_fr': 'Gratuit pour les membres actifs',
        'discount_info_de': 'Kostenlos für aktive Mitglieder',
        'icon':  'fas fa-bullhorn',
        'color': 'info',
        'partner_info':    'IESA Media Platform',
        'partner_info_en': 'IESA Media Platform',
        'partner_info_uk': 'Медіаплатформа IESA',
        'partner_info_fr': 'Plateforme médias IESA',
        'partner_info_de': 'IESA-Mediaplattform',
        'terms':    'Available to members with active membership and consistent participation history.',
        'terms_en': 'Available to members with active membership and consistent participation history.',
        'terms_uk': 'Доступно для членів з активним членством та активною участю в житті асоціації.',
        'terms_fr': 'Disponible pour les membres ayant un statut actif et un historique de participation régulier.',
        'terms_de': 'Verfügbar für Mitglieder mit aktiver Mitgliedschaft und regelmäßiger Teilnahmehistorie.',
        'is_active': True,
        'order': 4,
    },
]


def add_benefits(apps, schema_editor):
    MemberBenefit = apps.get_model('core', 'MemberBenefit')
    for data in BENEFITS:
        MemberBenefit.objects.get_or_create(
            title_en=data['title_en'],
            defaults=data,
        )


def remove_benefits(apps, schema_editor):
    MemberBenefit = apps.get_model('core', 'MemberBenefit')
    en_titles = [b['title_en'] for b in BENEFITS]
    MemberBenefit.objects.filter(title_en__in=en_titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_memberbenefit_partner_info_de_and_more'),
    ]

    operations = [
        migrations.RunPython(add_benefits, remove_benefits),
    ]
