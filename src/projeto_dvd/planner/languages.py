"""Language tags as the DVD wants them: ISO 639-1, two lowercase letters."""

# ISO 639-2 (bibliographic and terminology codes) to ISO 639-1, for the common languages.
ISO_639_2 = {
    "por": "pt", "eng": "en", "spa": "es", "fre": "fr", "fra": "fr", "ger": "de", "deu": "de",
    "ita": "it", "jpn": "ja", "kor": "ko", "chi": "zh", "zho": "zh", "rus": "ru", "dut": "nl",
    "nld": "nl", "swe": "sv", "nor": "no", "dan": "da", "fin": "fi", "pol": "pl", "tur": "tr",
    "ara": "ar", "heb": "he", "hin": "hi", "tha": "th", "cze": "cs", "ces": "cs", "hun": "hu",
    "gre": "el", "ell": "el", "rum": "ro", "ron": "ro", "ukr": "uk", "vie": "vi", "ind": "id",
    "may": "ms", "msa": "ms", "cat": "ca", "glg": "gl", "baq": "eu", "eus": "eu", "hrv": "hr",
    "srp": "sr", "slv": "sl", "slo": "sk", "slk": "sk", "bul": "bg", "ice": "is", "isl": "is",
    "est": "et", "lav": "lv", "lit": "lt", "lat": "la", "tgl": "tl", "fil": "tl",
}  # fmt: skip
ISO_639_1 = frozenset(ISO_639_2.values())


def dvd_language(tag: str | None) -> str | None:
    """'por', 'pt-BR' or 'en.forced' as 'pt'/'en'; None when unknown."""
    if not tag:
        return None
    head = tag.replace("_", "-").split("-")[0].split(".")[0].lower()
    if head in ISO_639_1:
        return head
    return ISO_639_2.get(head)


UNKNOWN_LANGUAGE = "Idioma não informado"
# Portuguese names for the menus and the screens; other codes show in upper case.
LANGUAGE_NAMES = {
    "pt": "Português", "en": "Inglês", "es": "Espanhol", "fr": "Francês", "de": "Alemão",
    "it": "Italiano", "ja": "Japonês", "ko": "Coreano", "zh": "Chinês", "ru": "Russo",
    "nl": "Holandês", "sv": "Sueco", "no": "Norueguês", "da": "Dinamarquês", "fi": "Finlandês",
    "pl": "Polonês", "tr": "Turco", "ar": "Árabe", "he": "Hebraico", "hi": "Hindi",
    "th": "Tailandês", "cs": "Tcheco", "hu": "Húngaro", "el": "Grego", "ro": "Romeno",
    "uk": "Ucraniano", "vi": "Vietnamita", "id": "Indonésio", "ca": "Catalão",
}  # fmt: skip


def language_name(code: str) -> str:
    """'pt' as 'Português'; 'und' (no language) as 'Idioma não informado'."""
    if code == "und":
        return UNKNOWN_LANGUAGE
    return LANGUAGE_NAMES.get(code, code.upper())
