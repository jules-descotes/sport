"""Le client CANDHIS et le compteur de quota.

Les réponses sont **mockées**, et calquées sur les exemples de la documentation
du Cerema (cf. docs/CANDHIS.md). Ce qui est éprouvé ici, ce sont les quatre
pièges de cette API — `success` à 200, le 999.9999, l'en-tête variable, la
journée comme granularité — plus la règle qui les tient tous : pas un appel
hors du compteur.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest

from app.services import candhis as candhis_module
from app.services.candhis import (
    CandhisClient,
    CandhisDisabled,
    CandhisError,
    clean_number,
    column_for,
    day_chunks,
    normalize_label,
    parse_envelope,
    parse_timestamp,
)
from app.services.quota import QuotaExhausted, remaining, reserve, used_today

# --- Exemples de la documentation, recopiés ------------------------------

TR_DIRECTIONNEL_H13 = {
    "apiVer": "1.00",
    "success": True,
    "message": "Données TR directionnel H13 campagne `06402` du 2026-09-14 au 2026-09-14",
    "nbLig": 2,
    "entete": [
        "Date",
        "H1/3 (m)",
        "Hmax (m)",
        "TH1/3 (s)",
        "Dir. au pic (°)",
        "Etal. au pic (°)",
        "Temp. mer (°C)",
    ],
    "results": [
        ["2026-09-14 08:00", "1.1000", "1.9000", "11.6000", "260.0000", "19.0000", "10.4000"],
        ["2026-09-14 08:30", "1.2000", "999.9999", "11.8000", "265.0000", "18.0000", "999.9999"],
    ],
}

TR_DIRECTIONNEL_HM0 = {
    "apiVer": "1.00",
    "success": "True",
    "message": "Données TR directionnel Hm0",
    "nbLig": 1,
    "entete": [
        "Date",
        "Hm0 (m)",
        "Hmax (m)",
        "T02 (s)",
        "Dir. au pic (°)",
        "Temp. mer (°C)",
    ],
    "results": [["2021-08-25 06:56", "0.8000", "999.9999", "3.2000", "46.0000", "999.9999"]],
}

TR_NON_DIRECTIONNEL = {
    "apiVer": "1.00",
    "success": True,
    "message": "Données TR non directionnel H13",
    "nbLig": 1,
    "entete": ["Date", "H1/3 (m)", "Hmax (m)", "TH1/3 (s)", "T. au pic (s)", "Temp. mer (°C)"],
    "results": [["2022-03-12 15:30", "2.2000", "3.5000", "11.0000", "16.7000", "999.9999"]],
}

# `getCampZone.php` : `results` est une liste **plate** de chaînes.
ZONE = {
    "apiVer": "1.00",
    "success": True,
    "message": "Liste des campagnes dans la zone Z07",
    "nbLig": 3,
    "entete": ["N° campagne"],
    "results": ["06401", "06402", "06403"],
}

AUCUNE_DONNEE = {
    "apiVer": "1.00",
    "success": False,
    "message": "Pas de données pour la campagne `06402` du 2027-03-26 au 2027-03-27",
    "nbLig": 0,
    "entete": None,
    "results": None,
}


def mock_transport(payload, status_code: int = 200, spy: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if spy is not None:
            spy.append(request)
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


# --- Normalisation des libellés ------------------------------------------


@pytest.mark.parametrize(
    "label, expected",
    [
        ("Hm0 (m)", "hm0m"),
        ("H1/3 (m)", "h13m"),
        ("Dir. au pic (°)", "diraupic"),
        ("Etal. au pic (°)", "etalaupic"),
        ("Temp. mer (°C)", "tempmerc"),
        ("TH1/3 (s)", "th13s"),
    ],
)
def test_labels_reduce_to_a_comparable_form(label: str, expected: str) -> None:
    assert normalize_label(label) == expected


def test_the_same_label_written_differently_still_maps() -> None:
    """Les en-têtes sont des intitulés humains, pas un contrat.

    Le degré peut s'écrire `(°)` ou `(deg)`, l'espace peut sauter. Aucune de
    ces variantes ne doit faire perdre une colonne.
    """
    assert column_for("Dir. au pic (°)") == "wave_direction_deg"
    assert column_for("Dir au pic(deg)") == "wave_direction_deg"
    assert column_for("DIR. AU PIC") == "wave_direction_deg"


def test_h13_and_hm0_share_a_column_but_periods_do_not() -> None:
    """Deux estimateurs de la même grandeur, trois périodes différentes.

    `H1/3` et `Hm0` sont deux façons d'estimer la hauteur significative : même
    colonne. Les périodes, non — `T02` est une moyenne et va dans
    `mean_period_s` ; `T. au pic` est le pic du spectre et `TH1/3` en tient
    lieu à défaut, les deux dans `peak_period_s`. Ranger `TH1/3` avec `T02`
    serait une erreur de grandeur.
    """
    assert column_for("H1/3 (m)") == column_for("Hm0 (m)") == "hm0_m"
    assert column_for("TH1/3 (s)") == "peak_period_s"
    assert column_for("T02 (s)") == "mean_period_s"
    assert column_for("T. au pic (s)") == "peak_period_s"


def test_an_unknown_column_is_ignored_not_guessed() -> None:
    assert column_for("Salinité (PSU)") is None


# --- La valeur manquante --------------------------------------------------


def test_the_sentinel_is_read_as_missing() -> None:
    """999.9999 est un code d'absence, pas une mesure.

    Le prendre au premier degré donnerait une mer à 1 000 °C. Il apparaît sur
    `Hmax` et sur la température dans les exemples du Cerema eux-mêmes.
    """
    assert clean_number("999.9999") is None
    assert clean_number("1.1000") == pytest.approx(1.1)
    assert clean_number("") is None
    assert clean_number(None) is None
    assert clean_number("pas un nombre") is None


def test_a_real_value_close_to_the_sentinel_is_kept() -> None:
    """Le seuil ne doit pas manger une mesure plausible."""
    assert clean_number("360.0") == pytest.approx(360.0)


# --- L'enveloppe ----------------------------------------------------------


def test_success_false_raises_even_on_http_200() -> None:
    """Le piège central de cette API.

    « Pas de données » répond **HTTP 200**. Un client qui ne lirait que le code
    HTTP écrirait une passe vide en croyant avoir réussi.
    """
    with pytest.raises(CandhisError) as exc:
        parse_envelope(AUCUNE_DONNEE)
    assert "Pas de données" in str(exc.value)


def test_success_is_accepted_as_bool_or_string() -> None:
    """L'API écrit `True`, `"True"` et `true` — les trois dans sa doc."""
    assert parse_envelope(TR_DIRECTIONNEL_H13).success is True
    assert parse_envelope(TR_DIRECTIONNEL_HM0).success is True
    assert parse_envelope({**TR_NON_DIRECTIONNEL, "success": "true"}).success is True


def test_a_response_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(CandhisError):
        parse_envelope(["pas", "un", "objet"])


def test_success_true_without_a_table_is_refused() -> None:
    with pytest.raises(CandhisError):
        parse_envelope({"success": True, "message": "ok", "entete": None, "results": None})


def test_a_flat_results_list_is_not_read_character_by_character() -> None:
    """`getCampZone.php` rend une liste plate de chaînes, pas des lignes."""
    rows = parse_envelope(ZONE).rows()
    assert [row["N° campagne"] for row in rows] == ["06401", "06402", "06403"]


def test_a_row_of_the_wrong_length_keeps_its_common_part() -> None:
    """Une colonne ajoutée en fin de tableau ne doit pas faire perdre la houle."""
    payload = {
        **TR_DIRECTIONNEL_H13,
        "results": [["2026-09-14 08:00", "1.1000", "1.9000", "11.6000", "260.0000"]],
    }
    measurements = parse_envelope(payload).measurements()
    assert len(measurements) == 1
    assert measurements[0].values["hm0_m"] == pytest.approx(1.1)


def test_a_row_that_is_not_a_list_is_skipped_not_fatal() -> None:
    payload = {**TR_DIRECTIONNEL_H13, "results": [{"inattendu": 1}]}
    assert parse_envelope(payload).measurements() == []


def test_a_row_without_a_readable_date_is_skipped() -> None:
    payload = {
        **TR_DIRECTIONNEL_H13,
        "results": [["pas une date", "1.1", "1.9", "11.6", "260", "19", "10.4"]],
    }
    assert parse_envelope(payload).measurements() == []


# --- Les trois formes de mesure ------------------------------------------


def test_directional_h13_maps_every_column() -> None:
    measurements = parse_envelope(TR_DIRECTIONNEL_H13).measurements()
    assert len(measurements) == 2

    first = measurements[0]
    assert first.ts == datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
    assert first.values["hm0_m"] == pytest.approx(1.1)
    assert first.values["wave_height_max_m"] == pytest.approx(1.9)
    assert first.values["peak_period_s"] == pytest.approx(11.6)
    assert first.values["wave_direction_deg"] == pytest.approx(260.0)
    assert first.values["directional_spread_deg"] == pytest.approx(19.0)
    assert first.values["water_temperature_c"] == pytest.approx(10.4)

    # La deuxième ligne porte deux sentinelles : elles deviennent des absences,
    # le reste de la ligne est conservé.
    second = measurements[1]
    assert second.values["wave_height_max_m"] is None
    assert second.values["water_temperature_c"] is None
    assert second.values["hm0_m"] == pytest.approx(1.2)


def test_directional_hm0_uses_the_mean_period() -> None:
    measurement = parse_envelope(TR_DIRECTIONNEL_HM0).measurements()[0]
    assert measurement.values["hm0_m"] == pytest.approx(0.8)
    assert measurement.values["mean_period_s"] == pytest.approx(3.2)
    assert measurement.values.get("peak_period_s") is None
    # Un horodatage non aligné sur la demi-heure : on lit la colonne Date, on
    # ne déduit pas l'heure d'un rang.
    assert measurement.ts == datetime(2021, 8, 25, 6, 56, tzinfo=UTC)


def test_non_directional_has_no_direction_at_all() -> None:
    measurement = parse_envelope(TR_NON_DIRECTIONNEL).measurements()[0]
    assert measurement.values["hm0_m"] == pytest.approx(2.2)
    assert "wave_direction_deg" not in measurement.values


def test_the_true_peak_period_wins_over_th13() -> None:
    """Le houlographe non directionnel publie les deux, et elles diffèrent.

    `TH1/3` vaut 11,0 s et `T. au pic` 16,7 s sur la même ligne. Retenir la
    premiere venue se tromperait de cinq secondes sur la grandeur qui decide
    si une houle est exploitable.
    """
    measurement = parse_envelope(TR_NON_DIRECTIONNEL).measurements()[0]
    assert measurement.values["peak_period_s"] == pytest.approx(16.7)


def test_th13_is_the_fallback_when_there_is_no_peak_period() -> None:
    """Les deux bouees de la cote basque ne publient que `TH1/3`.

    Sans ce repli, la bouee maison n'aurait aucune periode et la calibration
    des periodes n'aurait jamais rien a comparer.
    """
    measurement = parse_envelope(TR_DIRECTIONNEL_H13).measurements()[0]
    assert measurement.values["peak_period_s"] == pytest.approx(11.6)


def test_a_sentinel_peak_period_does_not_erase_a_measured_th13() -> None:
    """Une meilleure colonne vide ne vaut pas mieux qu'une moins bonne remplie."""
    payload = {
        **TR_NON_DIRECTIONNEL,
        "results": [
            ["2022-03-12 15:30", "2.2000", "3.5000", "11.0000", "999.9999", "12.0"]
        ],
    }
    measurement = parse_envelope(payload).measurements()[0]
    assert measurement.values["peak_period_s"] == pytest.approx(11.0)


def test_the_raw_row_is_kept_whole() -> None:
    """`raw` garde le libellé d'origine : c'est ce qui rendra `H1/3` récupérable."""
    measurement = parse_envelope(TR_DIRECTIONNEL_H13).measurements()[0]
    assert measurement.raw["H1/3 (m)"] == "1.1000"
    assert measurement.raw["Etal. au pic (°)"] == "19.0000"


def test_an_all_sentinel_row_is_recognised_as_empty() -> None:
    payload = {
        **TR_DIRECTIONNEL_H13,
        "results": [
            ["2026-09-14 09:00", "999.9999", "999.9999", "999.9999", "999.9999", "999.9999", "999.9999"]
        ],
    }
    assert parse_envelope(payload).measurements()[0].is_empty is True


# --- Horodatages ----------------------------------------------------------


def test_timestamps_are_read_in_utc_by_default() -> None:
    assert parse_timestamp("2026-09-14 08:00") == datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
    assert parse_timestamp("2026-09-14 08:00:00") == datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


def test_the_timezone_is_configurable_because_it_is_undocumented(monkeypatch) -> None:
    """Le Cerema ne publie pas son fuseau (cf. docs/CANDHIS.md §5).

    La variable existe pour corriger sans redéployer le jour où la mesure dirait
    le contraire d'UTC.
    """
    monkeypatch.setattr(candhis_module.settings, "candhis_tz", "Europe/Paris")
    # Le 14 septembre, Paris est à UTC+2.
    assert parse_timestamp("2026-09-14 08:00") == datetime(2026, 9, 14, 6, 0, tzinfo=UTC)


def test_an_unknown_timezone_falls_back_to_utc_instead_of_dying(monkeypatch) -> None:
    monkeypatch.setattr(candhis_module.settings, "candhis_tz", "Mars/Olympus")
    assert parse_timestamp("2026-09-14 08:00") == datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


# --- Découpage en tranches de 12 mois ------------------------------------


def test_a_short_range_is_a_single_chunk() -> None:
    assert day_chunks(date(2026, 9, 1), date(2026, 9, 14)) == [
        (date(2026, 9, 1), date(2026, 9, 14))
    ]


def test_chunks_never_overlap_and_cover_everything() -> None:
    chunks = day_chunks(date(2023, 1, 1), date(2026, 9, 14))
    assert chunks[0][0] == date(2023, 1, 1)
    assert chunks[-1][1] == date(2026, 9, 14)
    for previous, following in zip(chunks, chunks[1:]):
        # Une journée exactement entre deux tranches : ni trou ni doublon.
        assert (following[0] - previous[1]).days == 1
    for start, end in chunks:
        assert (end - start).days <= 366


def test_an_inverted_range_yields_nothing() -> None:
    assert day_chunks(date(2026, 9, 14), date(2026, 9, 1)) == []


# --- Le compteur de quota -------------------------------------------------


async def test_the_counter_persists_across_calls(db_session) -> None:
    await reserve(db_session, "candhis", cap=5)
    await reserve(db_session, "candhis", cap=5)
    assert await used_today(db_session, "candhis") == 2
    assert await remaining(db_session, "candhis", cap=5) == 3


async def test_the_141st_call_of_the_day_is_refused(db_session) -> None:
    """Le test que demandait le cadrage : le 141ᵉ appel est refusé.

    Et il l'est **sans toucher au réseau** — le refus vient du compteur, qui
    est interrogé avant que la requête ne parte.
    """
    for _ in range(140):
        await reserve(db_session, "candhis", cap=140)
    assert await used_today(db_session, "candhis") == 140

    with pytest.raises(QuotaExhausted):
        await reserve(db_session, "candhis", cap=140)

    # Refusé veut dire refusé : rien n'a été consommé de plus.
    assert await used_today(db_session, "candhis") == 140


async def test_the_counter_is_per_day(db_session) -> None:
    await reserve(db_session, "candhis", cap=2, day=date(2026, 9, 14))
    await reserve(db_session, "candhis", cap=2, day=date(2026, 9, 14))
    # Le lendemain repart à zéro, sans rien effacer de la veille.
    await reserve(db_session, "candhis", cap=2, day=date(2026, 9, 15))
    assert await used_today(db_session, "candhis", day=date(2026, 9, 14)) == 2
    assert await used_today(db_session, "candhis", day=date(2026, 9, 15)) == 1


async def test_the_counter_is_per_provider(db_session) -> None:
    await reserve(db_session, "candhis", cap=1)
    # Un autre fournisseur a son propre plafond, il ne consomme pas celui-ci.
    await reserve(db_session, "autre", cap=1)
    assert await used_today(db_session, "candhis") == 1
    assert await used_today(db_session, "autre") == 1


# --- Le client ------------------------------------------------------------


async def test_without_a_key_nothing_is_called(db_session) -> None:
    """Sans clé, la fonctionnalité est éteinte — et rien ne plante.

    Ni exception réseau, ni appel parti, ni quota consommé : `CandhisDisabled`,
    que l'appelant traite comme « pas de bouée aujourd'hui ».
    """
    spy: list[httpx.Request] = []
    transport = mock_transport(TR_DIRECTIONNEL_H13, spy=spy)

    async with httpx.AsyncClient(transport=transport) as http:
        client = CandhisClient(db_session, client=http, api_key="")
        assert client.enabled is False
        with pytest.raises(CandhisDisabled):
            await client.real_time("06402", date(2026, 9, 14))

    assert spy == []
    assert await used_today(db_session, "candhis") == 0


async def test_every_call_goes_through_the_counter(db_session) -> None:
    spy: list[httpx.Request] = []
    transport = mock_transport(TR_DIRECTIONNEL_H13, spy=spy)

    async with httpx.AsyncClient(transport=transport) as http:
        client = CandhisClient(db_session, client=http, api_key="jeton", cap=140)
        await client.real_time("06402", date(2026, 9, 14))
        await client.real_time("06402", date(2026, 9, 14))

    assert len(spy) == 2
    assert await used_today(db_session, "candhis") == 2


async def test_the_call_over_the_cap_never_reaches_the_network(db_session) -> None:
    spy: list[httpx.Request] = []
    transport = mock_transport(TR_DIRECTIONNEL_H13, spy=spy)

    async with httpx.AsyncClient(transport=transport) as http:
        client = CandhisClient(db_session, client=http, api_key="jeton", cap=2)
        await client.real_time("06402", date(2026, 9, 14))
        await client.real_time("06402", date(2026, 9, 14))
        with pytest.raises(QuotaExhausted):
            await client.real_time("06402", date(2026, 9, 14))

    assert len(spy) == 2


async def test_the_token_travels_bare_in_the_authorization_header(db_session) -> None:
    """Sans `Bearer` : c'est l'exemple curl de la documentation du Cerema."""
    spy: list[httpx.Request] = []
    transport = mock_transport(TR_DIRECTIONNEL_H13, spy=spy)

    async with httpx.AsyncClient(transport=transport) as http:
        client = CandhisClient(db_session, client=http, api_key="un-jeton-uuid")
        await client.real_time("06402", date(2026, 9, 14))

    assert spy[0].headers["Authorization"] == "un-jeton-uuid"


async def test_datefin_is_always_sent(db_session) -> None:
    """Sans `dateFin`, l'API répondrait **douze mois** au lieu d'une journée."""
    spy: list[httpx.Request] = []
    transport = mock_transport(TR_DIRECTIONNEL_H13, spy=spy)

    async with httpx.AsyncClient(transport=transport) as http:
        client = CandhisClient(db_session, client=http, api_key="jeton")
        await client.real_time("06402", date(2026, 9, 14))

    assert spy[0].url.params["dateDeb"] == "2026-09-14"
    assert spy[0].url.params["dateFin"] == "2026-09-14"


@pytest.mark.parametrize(
    "status, expected",
    [(429, "quota"), (423, "bannie"), (401, "jeton")],
)
async def test_the_refusal_codes_are_named_not_just_raised(
    db_session, status: int, expected: str
) -> None:
    """423 veut dire IP bannie. Ça se lit dans un journal, pas dans une pile."""
    transport = mock_transport({}, status_code=status)

    async with httpx.AsyncClient(transport=transport) as http:
        client = CandhisClient(db_session, client=http, api_key="jeton")
        with pytest.raises(CandhisError) as exc:
            await client.real_time("06402", date(2026, 9, 14))

    assert expected in str(exc.value)


async def test_a_body_that_is_not_json_is_reported_not_crashed(db_session) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = CandhisClient(db_session, client=http, api_key="jeton")
        with pytest.raises(CandhisError):
            await client.real_time("06402", date(2026, 9, 14))


async def test_an_unexpected_payload_shape_is_an_error_not_a_traceback(
    db_session,
) -> None:
    """Un format inattendu se signale, il ne casse pas la passe.

    L'appelant attrape `CandhisError` et journalise ; le job continue. C'est la
    différence entre « la bouée n'a rien dit ce matin » et « le service est
    tombé ».
    """
    transport = mock_transport({"apiVer": "2.00", "donnees": []})

    async with httpx.AsyncClient(transport=transport) as http:
        client = CandhisClient(db_session, client=http, api_key="jeton")
        with pytest.raises(CandhisError):
            await client.real_time("06402", date(2026, 9, 14))
