"""Public portal adapters. No logins, browser workers or challenge bypasses."""

import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from .models import HOSTS, Listing, city_name, safe_url, slug


class SourceError(Exception):
    """A safe, user-visible explanation without response bodies or credentials."""


@dataclass
class Page:
    listings: list[Listing]
    next_url: str | None = None
    partial: bool = False
    total: int | None = None

    def dump(self):
        return {
            "listings": [asdict(x) for x in self.listings],
            "next_url": self.next_url,
            "partial": self.partial,
            "total": self.total,
        }

    @classmethod
    def load(cls, data):
        return cls(
            [Listing(**x) for x in data["listings"]],
            data.get("next_url"),
            data.get("partial", False),
            data.get("total"),
        )


def number(value):
    if value is None:
        return None
    text = re.sub(r"[\s'’]", "", str(value)).strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def capture(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE)
    return number(match[1]) if match else None


def search_url(source: str, city: str):
    town = slug(city_name(city))
    # These portals use different official slugs for Wetzikon.
    place = "wetzikon-zh" if town == "wetzikon" else slug(city)
    root = "https://" + HOSTS[source]
    if source == "rentumo":
        location = "wetzikon-kanton-zuerich" if town == "wetzikon" else town
        return root + "/mietobjekte?" + urlencode({"location": location})
    if source == "rentola":
        return root + "/en/for-rent/" + ("wetzikon-zh" if town == "wetzikon" else town)
    if source == "huusbro":
        return root + "/de/mieten/" + town
    if source == "homegate":
        return root + "/mieten/wohnung/ort-" + place + "/trefferliste"
    if source == "immoscout24":
        return root + "/de/wohnung/mieten/ort-" + place
    if source == "realadvisor":
        return root + "/de/mieten/stadt-" + place + "/wohnung"
    if source == "homematch":
        return root + "/de/mieten/wohnung/ort-" + place
    return root + "/en/search/?" + urlencode({"query": city, "offerType": "RENT"})


PATTERNS = {
    "rentola": r"^/en/listings/[^/]+$",
    "rentumo": r"^/inserate/[^/]+-\d+$",
    "huusbro": r"^/de/listings/[^/]+/[^/]+$",
    "homegate": r"^/(?:mieten|rent)/\d+",
    "immoscout24": r"^/(?:de/d|[a-z]{2}/wohnung-mieten)/[^?]+",
    "realadvisor": r"^/de/mieten/(?:wohnung|haus)/[^/]+$",
    "homematch": r"^/de/mieten/(?:wohnung|haus)/ort-[^/]+/\d+$",
}


def category(text):
    low = text.casefold()
    if re.search(
        r"\b(?:wg|tauschwohnung|wohnungstausch|lagerraum|single.room|shared.flat|einzelzimmer|parkplatz|garage|gewerbe)\b",
        low,
    ):
        return "other"
    return "house" if re.search(r"\b(?:haus|house|villa)\b", low) else "apartment"


def parse_html(source, url, body):
    soup = BeautifulSoup(body, "html.parser")
    if any(
        word in body[:15000].lower()
        for word in (
            "captcha-delivery.com",
            "please enable js and disable",
            "cf-chl-",
            "just a moment...",
        )
    ):
        raise SourceError("Сайт включил защиту от автоматических запросов")
    if source == "rentola":
        return parse_rentola(soup, url)
    found = {}
    # DOM cards include all visible listings; JSON-LD often includes only the first 10.
    for a in soup.find_all("a", href=re.compile(PATTERNS[source])):
        href = safe_url(urljoin(url, a["href"]), source)
        if href in found:
            continue
        if source == "rentumo":
            card = a.find_parent(attrs={"data-testid": "listing-card"})
        elif source in {"huusbro", "homematch"}:
            card = a.find("article") or a.find_parent("article")
        elif source == "realadvisor":
            card = a
        else:
            card = a.find_parent("article") or a
        if card is None:
            continue
        text = card.get_text(" ", strip=True)
        if not text:
            continue
        heading = card.find(["h2", "h3", "h4"])
        if source == "realadvisor":
            heading = card.select_one("div.col-span-full p.font-medium") or heading
        title = heading.get_text(" ", strip=True) if heading else text[:180]
        if source == "rentumo":
            blocks = list(card.stripped_strings)
            title = blocks[1] if len(blocks) > 1 else title
        rooms = capture(r"(\d+(?:[.,]\d+)?)\s*[- ]?\s*(?:Zimmer|rooms)", text)
        area = capture(r"(\d+(?:[.,]\d+)?)\s*m[²2]", text)
        price = capture(r"CHF\s*([\d][\d'’.,\s]*\d|\d)", text)
        note = "Цена из объявления; проверьте коммунальные расходы"
        gross = capture(r"brutto\s*CHF\s*([\d][\d'’.,\s]*\d|\d)", text)
        if gross is not None:
            price, note = gross, "Включая коммунальные расходы (brutto)"
        elif "inkl. NK" in text:
            note = "Включая коммунальные расходы (inkl. NK)"
        elif "exkl. NK" in text:
            note = "Без коммунальных расходов (exkl. NK)"
        address = ""
        city = ""
        if source == "huusbro" and heading:
            city = title.split(",")[-1].strip().replace("(", "").replace(")", "")
            pin = card.select_one(".lucide-map-pin")
            if pin and pin.parent:
                address = pin.parent.get_text(" ", strip=True)
        elif source == "rentumo":
            # The location is the first text block in the card, before its title.
            parts = list(card.stripped_strings)
            city = parts[0] if parts else ""
        else:
            # Address is a distinct text node, avoiding descriptions and nearby-city recommendations.
            for node in card.stripped_strings:
                match = re.search(r"\b\d{4}\s+([A-Za-zÀ-ž][A-Za-zÀ-ž .()'-]*)", node)
                if match:
                    address = node.strip()
                    city = match[1].strip().replace("(", "").replace(")", "")
                    break
        if city:
            found[href] = Listing(
                source,
                href,
                title[:240],
                city,
                address[:250],
                price,
                rooms,
                area,
                category(title),
                note,
            )
    if not found:
        # A schema-only page is supported when it supplies actual individual listings.
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                tree = json.loads(script.get_text())
            except (ValueError, TypeError):
                continue
            for item in schema_items(tree):
                href = item.get("url", "")
                if not href or not re.search(PATTERNS[source], urlsplit(href).path):
                    continue
                address = item.get("address") or {}
                offer = item.get("offers") or {}
                area = item.get("floorSize") or {}
                if not isinstance(address, dict) or not isinstance(offer, dict):
                    continue
                found[href] = Listing(
                    source,
                    safe_url(urljoin(url, href), source),
                    str(item.get("name", "Жильё"))[:240],
                    address.get("addressLocality", ""),
                    address.get("streetAddress", ""),
                    number(offer.get("price")),
                    number(item.get("numberOfRooms")),
                    number(area.get("value")) if isinstance(area, dict) else None,
                )
    if not found and not re.search(
        r"(?:keine|0)\s+(?:Mietwohnungen|Objekte|Angebote|Treffer|Immobilien)|keine\s+.*gefunden",
        soup.get_text(" "),
        re.IGNORECASE,
    ):
        raise SourceError("Структура страницы изменилась: объявления не распознаны")
    next_link = soup.select_one('a[rel="next"]')
    if not next_link:
        next_link = soup.find(
            "a",
            attrs={"aria-label": re.compile(r"(?:Next|Nächste|Weiter)", re.IGNORECASE)},
        )
    if not next_link:
        current = urlsplit(url).path.rstrip("/")
        match = re.search(r"/(\d+)$", current)
        target = (
            (current[: match.start()] if match else current)
            + "/"
            + str(int(match[1]) + 1 if match else 2)
        )
        next_link = soup.find("a", href=target)
    next_url = safe_url(urljoin(url, next_link["href"]), source) if next_link else None
    # A visible result total makes truncation explicit even if pagination isn't discoverable.
    total = None
    marker = soup.select_one('[data-testid="results-count"]')
    if marker:
        total = number(marker.get("data-filters-result-count"))
    for node in soup.find_all(["h1", "p"], limit=250):
        n = capture(
            r"([\d'’]+)\s+(?:Objekte gefunden|Treffer|Mietwohnungen gefunden)",
            node.get_text(" "),
        )
        if n is not None:
            total = n
            break
    inaccessible_cards = source == "realadvisor" and len(
        [c for c in soup.select("div.bg-card") if "CHF" in c.get_text()]
    ) > len(found)
    return Page(
        list(found.values()),
        next_url,
        inaccessible_cards,
        int(total) if total is not None else None,
    )


def schema_items(tree):
    if isinstance(tree, list):
        for item in tree:
            yield from schema_items(item)
    elif isinstance(tree, dict):
        if tree.get("@type") in {"RealEstateListing", "Apartment", "House"}:
            yield tree
        for key in ("@graph", "mainEntity", "itemListElement", "item"):
            if key in tree:
                yield from schema_items(tree[key])


def parse_rentola(soup, url):
    """Read the public search schema, including precise fractional-room titles."""
    found, structured_list = {}, False
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            tree = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue
        if isinstance(tree, dict) and tree.get("@type") == "SearchResultsPage":
            entity = tree.get("mainEntity")
            structured_list = structured_list or (
                isinstance(entity, dict)
                and isinstance(entity.get("itemListElement"), list)
            )
        for item in schema_items(tree):
            offers = item.get("offers")
            if not isinstance(offers, dict):
                continue
            offered = offers.get("itemOffered")
            if not isinstance(offered, dict):
                continue
            address, area = offered.get("address"), offered.get("floorSize")
            if (
                not isinstance(address, dict)
                or address.get("addressCountry") != "CH"
                or offers.get("priceCurrency") != "CHF"
            ):
                continue
            href = item.get("url", "")
            if not re.search(PATTERNS["rentola"], urlsplit(href).path):
                continue
            href = safe_url(urljoin(url, href), "rentola")
            title = str(item.get("name", "Жильё"))
            # numberOfBedrooms in the schema can be rounded (e.g. 3 for 2½ rooms).
            room_title = re.sub(r"(\d)\s*½", r"\1.5", title)
            rooms = capture(
                r"(\d+(?:[.,]\d+)?)\s*[- ]?\s*(?:rooms?|Zimmer|pièces?|pieces?)",
                room_title,
            )
            if rooms is None:
                counter = offered.get("numberOfRooms", offered.get("numberOfBedrooms"))
                rooms = (
                    number(counter.get("value"))
                    if isinstance(counter, dict)
                    else number(counter)
                )
            kind = {
                "Apartment": "apartment",
                "House": "house",
                "SingleFamilyResidence": "house",
            }.get(offered.get("@type"), "other")
            if category(title) == "other":
                kind = "other"
            found[href] = Listing(
                "rentola",
                href,
                title[:240],
                address.get("addressLocality", ""),
                address.get("streetAddress", "")[:250],
                number(offers.get("price")),
                rooms,
                number(area.get("value")) if isinstance(area, dict) else None,
                kind,
            )
    text = soup.get_text(" ", strip=True)
    # Only an explicit empty search is a successful zero; a removed schema is an error.
    total = capture(r"\b([\d'’]+)\s+results\b", text)
    if not found and not (structured_list and total == 0):
        raise SourceError(
            "Rentola: структура выдачи изменилась, объявления не распознаны"
        )
    current_page = int(parse_qs(urlsplit(url).query).get("page", ["1"])[0])
    next_url = None
    for link in soup.find_all("a", href=True):
        target = urlsplit(urljoin(url, link["href"]))
        if target.path == urlsplit(url).path and parse_qs(target.query).get("page") == [
            str(current_page + 1)
        ]:
            next_url = safe_url(urljoin(url, link["href"]), "rentola")
            break
    if total is None:
        # Without the result count, do not claim full coverage of a populated search.
        return Page(list(found.values()), next_url, partial=bool(found))
    return Page(list(found.values()), next_url, total=int(total))


def parse_flatfox(body):
    data = json.loads(body)
    rows = data if isinstance(data, list) else data.get("results")
    if not isinstance(rows, list):
        raise SourceError("Flatfox вернул неожиданный формат")
    found = []
    for row in rows:
        if (
            row.get("offer_type") != "RENT"
            or row.get("status") != "act"
            or row.get("price_unit") != "monthly"
        ):
            continue
        kind = row.get("object_category", "").lower()
        if (
            row.get("object_type") in {"SINGLE_ROOM", "SHARED_FLAT"}
            or row.get("is_swap")
            or category(row.get("description_title") or "") == "other"
        ):
            kind = "other"
        price = number(row.get("rent_gross"))
        note = "Включая коммунальные расходы"
        if (
            price is None
            and row.get("rent_net") is not None
            and row.get("rent_charges") is not None
        ):
            price = number(row["rent_net"]) + number(row["rent_charges"])
        if price is None:
            price = number(row.get("price_display"))
            note = "Цена из объявления; проверьте коммунальные расходы"
        if row.get("flatfox_priority_exclusive_until"):
            note += "; для раннего отклика может требоваться Flatfox Priority"
        found.append(
            Listing(
                "flatfox",
                safe_url(urljoin("https://flatfox.ch", row["url"]), "flatfox"),
                row.get("description_title") or row.get("short_title") or "Жильё",
                row.get("city", ""),
                row.get("public_address", ""),
                price,
                number(row.get("number_of_rooms")),
                number(row.get("surface_living")),
                kind,
                note,
            )
        )
    return Page(found)
