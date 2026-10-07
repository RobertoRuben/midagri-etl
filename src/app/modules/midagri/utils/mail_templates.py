"""Contenido de los correos de inicio, fin e incidencias de una ejecución (funciones puras, sin I/O).

Diseño de informe: cabecera institucional, franja de estado, indicadores, tabla por mercado con totales y pie formal.
HTML con tablas y estilos en línea para que se vea igual en Outlook, Gmail y clientes móviles.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from app.modules.midagri.dto.response.etl_run_response import (
    EtlRunDetailResponse,
    LogEventResponse,
    PriceLoadResponse,
)
from app.modules.midagri.model.pg.enums import EventLevel, LoadStatus, RunStatus, RunTrigger

LIMA = ZoneInfo("America/Lima")

SYSTEM_NAME = "SISAP · Precios de mercado"
"""Nombre del proceso en la cabecera y el asunto."""

_FONT = "Segoe UI,Helvetica,Arial,sans-serif"
_INK = "#1F2933"  # texto principal
_MUTED = "#5F6B7A"  # etiquetas y texto secundario
_LINE = "#DDE1E6"  # bordes
_SOFT = "#F5F6F8"  # fondos de encabezado de tabla y página
_BRAND = "#16263D"  # cabecera y botón

_RUN_STATUS: dict[RunStatus, tuple[str, str, str, str]] = {
    # estado: (título, asunto, color, fondo)
    RunStatus.QUEUED: ("En cola", "en cola", "#3D5A80", "#EEF3F9"),
    RunStatus.RUNNING: ("En curso", "iniciada", "#1F5FA8", "#EEF4FB"),
    RunStatus.OK: ("Completada sin incidencias", "completada", "#1E7045", "#EEF7F1"),
    RunStatus.PARTIAL: ("Completada con observaciones", "completada con observaciones", "#8A5A00", "#FFF7E6"),
    RunStatus.FAILED: ("Fallida", "fallida", "#B42318", "#FDF0EE"),
}
_LOAD_STATUS: dict[LoadStatus, tuple[str, str]] = {
    LoadStatus.OK: ("Correcto", "#1E7045"),
    LoadStatus.PARTIAL: ("Parcial", "#8A5A00"),
    LoadStatus.FAILED: ("Fallido", "#B42318"),
    LoadStatus.SKIPPED: ("Omitido", _MUTED),
}
_LEVEL_LABEL: dict[EventLevel, str] = {
    EventLevel.DEBUG: "Depuración",
    EventLevel.INFO: "Información",
    EventLevel.WARNING: "Advertencia",
    EventLevel.ERROR: "Error",
}
MAX_INCIDENTS_SHOWN = 50
"""Eventos que muestra el correo de incidencias; el resto se cuenta y queda en el log."""
_TRIGGER_LABEL: dict[RunTrigger, str] = {RunTrigger.CRON: "Tarea programada", RunTrigger.MANUAL: "Manual"}
_LOAD_COLUMNS = ("Mercado", "Estado", "Descargados", "Cargados", "Sin catálogo", "Errores")

_MOBILE_CSS = (
    "@media only screen and (max-width:520px){"
    ".pad{padding-left:16px!important;padding-right:16px!important}"
    ".desk{display:none!important}"
    ".mob{display:block!important;max-height:none!important;overflow:visible!important}"
    f".kpi{{display:inline-block!important;width:50%!important;box-sizing:border-box;border-left:0!important;"
    f"border-bottom:1px solid {_LINE}}}"
    "}"
)
"""Pantallas angostas (Gmail, iOS Mail): márgenes menores, indicadores en 2×2 y mercados como lista.

Outlook de escritorio ignora la media query y muestra la versión de escritorio.
"""


@dataclass(frozen=True, slots=True)
class MailContent:
    """Asunto y cuerpo (texto plano y HTML) de un correo."""

    subject: str
    text: str
    html: str


def build_start_mail(run: EtlRunDetailResponse, *, market_names: Mapping[str, str] | None = None) -> MailContent:
    """Correo de inicio: cuándo, quién lo disparó, periodo y mercados."""
    facts = _run_facts(run) + [("Inicio", _when(run.started_at))]
    markets = [_market(code, market_names) for code in run.market_codes]
    text = _text(
        run,
        "Inicio de ejecución",
        [
            _facts_text(facts),
            "",
            f"Mercados ({len(markets)}):",
            *(f"  - {_market_text(name, code)}" for name, code in markets),
        ],
    )
    body = _section("Datos de la ejecución", _facts_html(facts)) + _section(
        f"Mercados a procesar ({len(markets)})", _market_list_html(markets)
    )
    return MailContent(
        subject=_subject(run, "iniciada"),
        text=text,
        html=_page(
            run,
            title=f"Inicio de ejecución N.º {run.id}",
            summary=f"La ejecución comenzó el {_when(run.started_at)}. Recibirá otro correo con el resultado al finalizar.",
            body=body,
        ),
    )


def build_end_mail(
    run: EtlRunDetailResponse,
    *,
    logs_url: str,
    has_attachment: bool,
    market_names: Mapping[str, str] | None = None,
    auto_register: bool = False,
) -> MailContent:
    """Correo de fin: estado, indicadores, detalle por mercado, catálogo y enlace al registro de la ejecución.

    Args:
        auto_register: Si el ETL registra solo los faltantes en el catálogo (D36); cambia la indicación del adjunto.
    """
    facts = _run_facts(run) + [
        ("Inicio", _when(run.started_at)),
        ("Fin", _when(run.finished_at)),
        ("Duración", _duration(run.duration_ms)),
    ]
    kpis = [
        ("Precios descargados", run.fetched),
        ("Registros nuevos", run.inserted),
        ("Registros actualizados", run.updated),
        ("Sin producto en catálogo", run.unmatched),
    ]
    rows = [(*_market(load.market_code, market_names), load) for load in run.loads]
    catalog_lines = [_gaps(run)]
    if has_attachment:
        catalog_lines.append("Se adjunta el reporte de productos faltantes del periodo en formato Excel.")
        catalog_lines.append(
            "Los productos faltantes se registran automáticamente en el catálogo; el detalle está en el registro de "
            "la ejecución."
            if auto_register
            else "Para registrarlos, revise las hojas «Cultivos» y «Registro» del archivo y cárguelo en el sistema."
        )
    text = _text(
        run,
        "Resultado de ejecución",
        [
            _facts_text(facts),
            *([f"Error: {run.error}"] if run.error else []),
            "",
            "Indicadores:",
            *(f"  {label}: {_number(value)}" for label, value in kpis),
            "",
            "Detalle por mercado:",
            " | ".join(_LOAD_COLUMNS),
            *(
                " | ".join(
                    [
                        _market_text(name, code),
                        _LOAD_STATUS[load.status][0],
                        _number(load.fetched),
                        _number(load.inserted + load.updated),
                        _number(load.unmatched),
                        _number(load.errors),
                    ]
                )
                for name, code, load in rows
            ),
            "",
            "Catálogo de productos:",
            *(f"  {line}" for line in catalog_lines),
            "",
            f"Registro de la ejecución: {logs_url}",
        ],
    )
    body = (
        _kpis_html(kpis)
        + (_notice_html("Detalle de la incidencia", run.error, "#B42318", "#FDF0EE") if run.error else "")
        + _section("Detalle por mercado", _loads_html(rows))
        + _section("Catálogo de productos", "".join(_paragraph(line) for line in catalog_lines))
        + _section("Datos de la ejecución", _facts_html(facts))
        + _button_html("Ver registro de la ejecución", logs_url)
    )
    return MailContent(
        subject=_subject(run),
        text=text,
        html=_page(
            run,
            title=f"Resultado de ejecución N.º {run.id}",
            summary=_end_summary(run),
            body=body,
        ),
    )


def build_error_mail(
    run: EtlRunDetailResponse,
    events: Sequence[LogEventResponse],
    *,
    logs_url: str,
    market_names: Mapping[str, str] | None = None,
) -> MailContent:
    """Correo de incidencias (D37): el log de errores y advertencias, con la traza de cada excepción.

    Muestra los primeros `MAX_INCIDENTS_SHOWN` eventos, en orden, y cuenta los que se omiten.
    """
    errors = sum(event.level is EventLevel.ERROR for event in events)
    warnings = len(events) - errors
    counts = f"{_plural(errors, 'error', 'errores')} y {_plural(warnings, 'advertencia', 'advertencias')}"
    shown = list(events[:MAX_INCIDENTS_SHOWN])
    omitted = len(events) - len(shown)
    omitted_note = (
        f"Se muestran los primeros {len(shown)} eventos; se omitieron {_number(omitted)}. "
        "El log completo está en el registro de la ejecución."
        if omitted
        else ""
    )
    color, background = ("#B42318", "#FDF0EE") if errors else ("#8A5A00", "#FFF7E6")
    summary = f"Durante la ejecución hubo {counts}. Estado final: {_RUN_STATUS[run.status][0].lower()}."
    text_events = []
    for event in shown:
        text_events += [
            f"[{_LEVEL_LABEL[event.level].upper()}] {_when(event.created_at, seconds=True)}"
            f"{' · ' + _market_text(*_market(event.market_code, market_names)) if event.market_code else ''}"
            f" · {event.event}",
            f"  {event.message}",
        ]
        trace = _event_trace(event)
        if trace:
            text_events += ["  Traza:", *(f"    {line}" for line in trace.splitlines())]
        text_events.append("")
    text = _text(
        run,
        "Incidencias de la ejecución",
        [
            f"Hubo {counts}.",
            "",
            *text_events,
            *([omitted_note, ""] if omitted_note else []),
            f"Registro de la ejecución: {logs_url}",
        ],
    )
    body = (
        _section(
            f"Log de incidencias ({_number(len(events))})", "".join(_incident_html(e, market_names) for e in shown)
        )
        + (_paragraph(omitted_note) if omitted_note else "")
        + _section("Datos de la ejecución", _facts_html(_run_facts(run) + [("Inicio", _when(run.started_at))]))
        + _button_html("Ver registro completo de la ejecución", logs_url)
    )
    simulation = " (simulación)" if run.dry_run else ""
    return MailContent(
        subject=f"{SYSTEM_NAME} | Ejecución N.º {run.id}: {counts}{simulation}",
        text=text,
        html=_page(
            run,
            title=f"Incidencias de la ejecución N.º {run.id}",
            summary=summary,
            body=body,
            banner=("Errores" if errors else "Advertencias", color, background),
        ),
    )


# --- Texto --------------------------------------------------------------------------------------------------------


def _subject(run: EtlRunDetailResponse, outcome: str | None = None) -> str:
    """`outcome`: verbo fijo (el inicio siempre dice «iniciada»); si falta, el del estado de la ejecución."""
    simulation = " (simulación)" if run.dry_run else ""
    return f"{SYSTEM_NAME} | Ejecución N.º {run.id} {outcome or _RUN_STATUS[run.status][1]}{simulation}"


def _text(run: EtlRunDetailResponse, title: str, lines: Sequence[str]) -> str:
    header = [SYSTEM_NAME, f"{title} N.º {run.id}", f"Estado: {_RUN_STATUS[run.status][0]}", ""]
    footer = ["", "Mensaje automático del proceso de carga de precios SISAP. No responda a este correo."]
    return "\n".join([*header, *lines, *footer]).strip()


def _run_facts(run: EtlRunDetailResponse) -> list[tuple[str, str]]:
    trigger = _TRIGGER_LABEL[run.trigger] + (f" ({run.requested_by})" if run.requested_by else "")
    facts = [
        ("N.º de ejecución", str(run.id)),
        ("Periodo consultado", f"{run.date_from:%d/%m/%Y} al {run.date_to:%d/%m/%Y}"),
        ("Origen", trigger),
    ]
    if run.dry_run:
        facts.append(("Modo", "Simulación: no se escribe en la base de datos"))
    return facts


def _end_summary(run: EtlRunDetailResponse) -> str:
    finished = f"La ejecución finalizó el {_when(run.finished_at)} (duración: {_duration(run.duration_ms)})."
    if run.status is RunStatus.FAILED:
        return f"{finished} No se completó la carga; revise el detalle de la incidencia."
    if run.status is RunStatus.PARTIAL:
        return f"{finished} Algunos mercados o pasos no se completaron; revise el detalle."
    return finished


def _when(moment: datetime | None, *, seconds: bool = False) -> str:
    pattern = "%d/%m/%Y %H:%M:%S" if seconds else "%d/%m/%Y %H:%M"
    return moment.astimezone(LIMA).strftime(pattern) if moment else "—"


def _duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "—"
    minutes, seconds = divmod(round(duration_ms / 1000), 60)
    return f"{minutes} min {seconds} s" if minutes else f"{seconds} s"


def _number(value: int) -> str:
    return f"{value:,}"


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{_number(count)} {singular if count == 1 else plural}"


def _gaps(run: EtlRunDetailResponse) -> str:
    if run.gaps_esc1 is None and run.gaps_esc2 is None:
        return "No se calcularon los productos faltantes en esta ejecución."
    parts = []
    if run.gaps_esc2:
        parts.append(f"{_plural(run.gaps_esc2, 'variedad', 'variedades')} de cultivos ya registrados")
    if run.gaps_esc1:
        parts.append(f"{_plural(run.gaps_esc1, 'variedad', 'variedades')} de cultivos nuevos")
    if not parts:
        return "No hay productos con precio en el periodo que falten en el catálogo."
    return f"Productos con precio en el periodo que no están en el catálogo: {' y '.join(parts)}."


def _market(code: str, market_names: Mapping[str, str] | None) -> tuple[str, str]:
    """`(nombre, código)`; si el mercado no está en `BM_Market`, el nombre es el código."""
    name = market_names.get(code) if market_names else None
    return (name or code, code)


def _market_text(name: str, code: str) -> str:
    return f"{name} ({code})" if name != code else code


def _facts_text(facts: Sequence[tuple[str, str]]) -> str:
    return "\n".join(f"{name}: {value}" for name, value in facts)


# --- HTML ---------------------------------------------------------------------------------------------------------


def _page(
    run: EtlRunDetailResponse,
    *,
    title: str,
    summary: str,
    body: str,
    banner: tuple[str, str, str] | None = None,
) -> str:
    """Documento completo: cabecera, franja de estado, cuerpo y pie.

    Args:
        banner: `(título, color, fondo)` de la franja; por defecto, los del estado de la ejecución.
    """
    label, _, color, background = _RUN_STATUS[run.status]
    if banner is not None:
        label, color, background = banner
    generated = datetime.now(LIMA).strftime("%d/%m/%Y %H:%M")
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<style>{_MOBILE_CSS}</style></head>"
        f'<body style="margin:0;padding:0;background:{_SOFT};font-family:{_FONT};color:{_INK}">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_SOFT}">'
        '<tr><td align="center" style="padding:32px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:680px;background:#FFFFFF;border:1px solid {_LINE}">'
        # Cabecera
        f'<tr><td class="pad" style="background:{_BRAND};padding:22px 32px">'
        f'<div style="color:#AEBBCD;font-size:11px;letter-spacing:1.2px;text-transform:uppercase">{escape(SYSTEM_NAME)}</div>'
        f'<div style="color:#FFFFFF;font-size:20px;line-height:28px;font-weight:600;margin-top:6px">{escape(title)}</div>'
        "</td></tr>"
        # Franja de estado
        f'<tr><td class="pad" style="background:{background};border-left:4px solid {color};padding:14px 28px">'
        f'<div style="color:{color};font-size:14px;font-weight:700">{escape(label)}</div>'
        f'<div style="color:{_INK};font-size:13px;line-height:20px;margin-top:2px">{escape(summary)}</div>'
        "</td></tr>"
        f'<tr><td class="pad" style="padding:8px 32px 32px">{body}</td></tr>'
        # Pie
        f'<tr><td class="pad" style="border-top:1px solid {_LINE};background:{_SOFT};padding:16px 32px;color:{_MUTED};'
        'font-size:11px;line-height:17px">'
        "Mensaje automático del proceso de carga de precios SISAP. No responda a este correo.<br>"
        f"Generado el {generated} (hora de Lima)."
        "</td></tr>"
        "</table></td></tr></table></body></html>"
    )


def _section(title: str, content: str) -> str:
    return (
        f'<div style="margin-top:28px;padding-bottom:8px;border-bottom:1px solid {_LINE};color:{_INK};'
        f'font-size:12px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase">{escape(title)}</div>'
        f'<div style="margin-top:12px">{content}</div>'
    )


def _paragraph(text: str) -> str:
    return f'<p style="margin:0 0 8px;font-size:14px;line-height:21px;color:{_INK}">{escape(text)}</p>'


def _facts_html(facts: Sequence[tuple[str, str]]) -> str:
    rows = "".join(
        f'<tr><td style="padding:7px 0;color:{_MUTED};font-size:13px;width:38%;vertical-align:top">{escape(name)}</td>'
        f'<td style="padding:7px 0;color:{_INK};font-size:13px;line-height:19px;vertical-align:top">'
        f"{escape(value)}</td></tr>"
        for name, value in facts
    )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>'


def _kpis_html(kpis: Sequence[tuple[str, int]]) -> str:
    width = f"{100 // len(kpis)}%"
    cells = "".join(
        f'<td class="kpi" width="{width}" style="padding:16px 14px;vertical-align:top;'
        f'{"" if index == 0 else f"border-left:1px solid {_LINE};"}">'
        f'<div style="color:{_INK};font-size:22px;line-height:28px;font-weight:600">{_number(value)}</div>'
        f'<div style="color:{_MUTED};font-size:11px;line-height:15px;margin-top:4px">{escape(label)}</div></td>'
        for index, (label, value) in enumerate(kpis)
    )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin-top:24px;border:1px solid {_LINE}"><tr>{cells}</tr></table>'
    )


def _notice_html(title: str, message: str, color: str, background: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin-top:20px;background:{background};border-left:4px solid {color}">'
        f'<tr><td style="padding:12px 16px;font-size:13px;line-height:20px;color:{_INK}">'
        f'<strong style="color:{color}">{escape(title)}</strong><br>{escape(message)}</td></tr></table>'
    )


def _cell(content: str, *, align: str = "left", header: bool = False, bold: bool = False) -> str:
    style = f"padding:9px 8px;border-bottom:1px solid {_LINE};text-align:{align};vertical-align:top;"
    if header:
        return (
            f'<th style="{style}background:{_SOFT};color:{_MUTED};font-size:11px;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:0.4px">{content}</th>'
        )
    weight = "font-weight:700;" if bold else ""
    return f'<td style="{style}color:{_INK};font-size:13px;{weight}">{content}</td>'


def _loads_html(rows: Sequence[tuple[str, str, PriceLoadResponse]]) -> str:
    if not rows:
        return _paragraph("No se procesó ningún mercado.")
    head = "".join(
        _cell(escape(column), align="left" if index < 2 else "right", header=True)
        for index, column in enumerate(_LOAD_COLUMNS)
    )
    body = []
    for name, code, load in rows:
        label, color = _LOAD_STATUS[load.status]
        market = escape(name) + (
            f'<br><span style="color:{_MUTED};font-size:11px">{escape(code)}</span>' if name != code else ""
        )
        body.append(
            "<tr>"
            + _cell(market)
            + _cell(f'<span style="color:{color};font-weight:600">{escape(label)}</span>')
            + "".join(
                _cell(_number(value), align="right")
                for value in (load.fetched, load.inserted + load.updated, load.unmatched, load.errors)
            )
            + "</tr>"
        )
    loads = [load for _, _, load in rows]
    totals = (
        sum(load.fetched for load in loads),
        sum(load.inserted + load.updated for load in loads),
        sum(load.unmatched for load in loads),
        sum(load.errors for load in loads),
    )
    total_row = (
        "<tr>"
        + _cell("Total", bold=True)
        + _cell("")
        + "".join(_cell(_number(value), align="right", bold=True) for value in totals)
        + "</tr>"
    )
    desktop = (
        '<table class="desk" role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {_LINE};border-bottom:0;border-collapse:collapse">'
        f"<tr>{head}</tr>{''.join(body)}{total_row}</table>"
    )
    return desktop + _loads_mobile_html(rows, totals)


def _loads_mobile_html(rows: Sequence[tuple[str, str, PriceLoadResponse]], totals: Sequence[int]) -> str:
    """Los mismos datos como lista apilada, oculta salvo en pantallas angostas."""
    blocks = []
    for name, code, load in [*rows, ("Total", "", None)]:
        if load is None:
            label, color = "", _INK
            values = totals
        else:
            label, color = _LOAD_STATUS[load.status]
            values = (load.fetched, load.inserted + load.updated, load.unmatched, load.errors)
        metrics = " · ".join(
            f"{escape(column)} <strong>{_number(value)}</strong>"
            for column, value in zip(_LOAD_COLUMNS[2:], values, strict=True)
        )
        subtitle = " · ".join(part for part in (code if name != code else "", label) if part)
        blocks.append(
            f'<div style="padding:10px 0;border-bottom:1px solid {_LINE}">'
            f'<div style="color:{_INK};font-size:14px;font-weight:600">{escape(name)}</div>'
            + (f'<div style="color:{color};font-size:12px;margin-top:2px">{escape(subtitle)}</div>' if subtitle else "")
            + f'<div style="color:{_MUTED};font-size:12px;line-height:18px;margin-top:4px">{metrics}</div></div>'
        )
    return f'<div class="mob" style="display:none;max-height:0;overflow:hidden;mso-hide:all">{"".join(blocks)}</div>'


def _market_list_html(markets: Sequence[tuple[str, str]]) -> str:
    rows = "".join(
        f'<tr><td style="padding:7px 0;border-bottom:1px solid {_LINE};color:{_INK};font-size:13px">{escape(name)}</td>'
        f'<td style="padding:7px 0;border-bottom:1px solid {_LINE};color:{_MUTED};font-size:12px;text-align:right">'
        f"{escape(code) if name != code else ''}</td></tr>"
        for name, code in markets
    )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>'


def _event_trace(event: LogEventResponse) -> str | None:
    trace = (event.data or {}).get("traceback")
    return str(trace).rstrip() if trace else None


def _incident_html(event: LogEventResponse, market_names: Mapping[str, str] | None) -> str:
    """Un evento del log: nivel, hora, mercado y código; el mensaje; y la traza en monoespaciado si la hay."""
    color = "#B42318" if event.level is EventLevel.ERROR else "#8A5A00"
    meta = [_when(event.created_at, seconds=True)]
    if event.market_code:
        meta.append(_market_text(*_market(event.market_code, market_names)))
    meta.append(event.event)
    trace = _event_trace(event)
    trace_html = (
        f'<pre style="margin:10px 0 0;padding:10px 12px;background:{_SOFT};border:1px solid {_LINE};'
        "font-family:Consolas,Menlo,'Courier New',monospace;font-size:11px;line-height:16px;color:#2B3440;"
        f'white-space:pre-wrap;word-break:break-word">{escape(trace)}</pre>'
        if trace
        else ""
    )
    return (
        f'<div style="padding:12px 0 12px 12px;border-left:3px solid {color};margin-bottom:10px">'
        f'<div style="font-size:11px;color:{_MUTED}">'
        f'<strong style="color:{color};text-transform:uppercase;letter-spacing:0.5px">'
        f"{escape(_LEVEL_LABEL[event.level])}</strong> · {escape(' · '.join(meta))}</div>"
        f'<div style="margin-top:4px;font-size:13px;line-height:20px;color:{_INK}">{escape(event.message)}</div>'
        f"{trace_html}</div>"
    )


def _button_html(label: str, url: str) -> str:
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:28px"><tr>'
        f'<td style="background:{_BRAND};border-radius:3px">'
        f'<a href="{escape(url, quote=True)}" style="display:inline-block;padding:11px 22px;color:#FFFFFF;'
        f'font-family:{_FONT};font-size:13px;font-weight:600;text-decoration:none">{escape(label)}</a>'
        "</td></tr></table>"
    )
