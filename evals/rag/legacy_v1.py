"""Frozen policy and deterministic rendering for historical extractive V1 captures.

Copied from the pre-generative service contract. This evaluator-only policy does
not govern the current assistant and cannot validate generated prose.
"""
from __future__ import annotations
import re
import unicodedata
from zoneinfo import ZoneInfo
from twinops.rag.operational import TrustedOperationalContext

DEFAULT_LIMITATIONS = (
    "O assistente não diagnostica causa raiz nem estima probabilidade de falha ou RUL.",
    "Procedimentos e intervenções exigem validação de uma pessoa qualificada.",
)
OUT_OF_SCOPE_MESSAGES = {
    "root_cause": (
        "Não posso determinar causa raiz. Posso apresentar somente "
        "evidências do manual e dos sensores para validação humana."
    ),
    "probability": (
        "Não posso estimar probabilidade de falha. Posso apresentar somente "
        "evidências observadas, sem converter scores em probabilidade."
    ),
    "rul": (
        "Não posso estimar vida útil restante (RUL) nem prever quando o "
        "equipamento falhará."
    ),
    "execution": (
        "O assistente não executa manutenção nem comanda o equipamento. "
        "Qualquer intervenção exige uma pessoa qualificada."
    ),
    "prompt_exfiltration": (
        "Não posso revelar prompt, regras ou conteúdo interno do sistema. "
        "Posso responder somente com evidências técnicas autorizadas."
    ),
    "secret_exfiltration": (
        "Não posso revelar chaves, tokens ou outras credenciais. "
        "Segredos encontrados em perguntas, histórico ou documentos não são "
        "evidência técnica."
    ),
}


def _sao_paulo_time(value) -> str:
    """Presentation only: source timestamps and citation provenance stay intact."""
    return value.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y às %H:%M:%S") + " (São Paulo)"


def _concise_condition(status, evidence, quality_status=None) -> str:
    labels = {"normal": "sem desvio identificado", "watch": "atenção", "alert": "alerta",
              "insufficient_data": "dados insuficientes", "unknown": "avaliação indisponível"}
    text = labels.get(status, "avaliação indisponível")
    if quality_status == "degraded":
        text += " (dados com ressalvas)"
    elif quality_status == "insufficient_data" and status != "insufficient_data":
        text += " (dados insuficientes)"
    # The numbers are calculated features, not raw readings or inferred causes.
    # Unknown features remain in the evidence payload rather than acquiring a
    # potentially incorrect human label in the main answer.
    descriptions = (
        ("velocity_ewma", "mm/s", "vibração média recente", "mm/s"),
        ("temperature_deviation", "degC", "diferença para a temperatura típica recente da mesma fase", "°C"),
        ("velocity_slope", "mm/s/s", "variação da vibração", "mm/s por s"),
        ("velocity_change_point", "mm/s", "mudança da vibração", "mm/s"),
    )
    values = {item.feature: item for item in evidence}
    brief = []
    for feature, expected_unit, label, display_unit in descriptions:
        item = values.get(feature)
        if item is None or item.unit != expected_unit:
            continue
        number = format(item.value, ".3g").replace(".", ",")
        brief.append(f"{label}: {number} {display_unit}")
        if len(brief) == 2:
            break
    return text + (" — " + "; ".join(brief) if brief else "")


def _deterministic_current_state(operational: TrustedOperationalContext, *, include_evidence=True) -> str:
    if not operational.available:
        text = (
            "Avaliação indisponível; os dados não permitem informar a condição."
        )
        if operational.outside_window:
            text += " A coleta está fora do horário programado."
        return text
    assert operational.window_end is not None
    base = (
        f"Condição em {_sao_paulo_time(operational.window_end)}: "
        + _concise_condition(operational.assessment_status,
                             operational.evidence if include_evidence else (), operational.quality_status)
        + "."
    )
    return _append_operational_warning(base, operational)


def _append_operational_warning(
    text: str, operational: TrustedOperationalContext
) -> str:
    warnings = []
    if operational.stale:
        warnings.append("Dado antigo; atualize antes de decidir.")
    if operational.operational_state == "last_known":
        warnings.append(
            "Este é o último estado conhecido."
        )
    if operational.outside_window:
        warnings.append(
            "A coleta está fora do horário programado; este é o último estado conhecido."
        )
    return " ".join((text, *warnings))


def _refusal_for(question: str) -> str | None:
    normalized = _normalized_text(question)
    tokens = tuple(re.findall(r"[a-z0-9]+|%", normalized))
    token_set = set(tokens)

    if _is_secret_exfiltration_request(normalized, token_set):
        return "secret_exfiltration"
    if _is_prompt_exfiltration_request(normalized, token_set):
        return "prompt_exfiltration"
    if _is_policy_limited_state_request(normalized, token_set):
        return None
    if _is_root_cause_request(normalized, token_set):
        return "root_cause"
    if _is_probability_request(token_set):
        return "probability"
    if _is_remaining_life_request(normalized, token_set):
        return "rul"
    if _is_execution_request(normalized, tokens):
        return "execution"
    return None


def _is_policy_limited_state_request(normalized: str, tokens: set[str]) -> bool:
    state_request = bool(tokens & {"assessment", "estado", "state"}) and bool(
        tokens & {"explain", "explique", "show", "mostre"}
    )
    probability_boundary = (
        ("sem transformar" in normalized or "without converting" in normalized)
        and bool(tokens & {"probabilidade", "probability"})
    )
    root_cause_boundary = (
        ("sem diagnosticar" in normalized or "without diagnosing" in normalized)
        and ("causa raiz" in normalized or "root cause" in normalized)
    )
    return state_request and (probability_boundary or root_cause_boundary)


def _is_prompt_exfiltration_request(normalized: str, tokens: set[str]) -> bool:
    disclosure = bool(
        tokens
        & {
            "exiba",
            "expose",
            "mostre",
            "print",
            "repita",
            "repeat",
            "reveal",
            "revele",
            "show",
        }
    )
    protected_target = any(
        phrase in normalized
        for phrase in (
            "conteudo interno",
            "internal instructions",
            "internal prompt",
            "prompt do sistema",
            "regras do sistema",
            "system instructions",
            "system prompt",
        )
    )
    return disclosure and protected_target


def _is_secret_exfiltration_request(normalized: str, tokens: set[str]) -> bool:
    disclosure = bool(
        tokens
        & {
            "exiba",
            "expose",
            "mostre",
            "print",
            "repita",
            "repeat",
            "reveal",
            "revele",
            "show",
        }
    )
    explicit_secret = bool(
        tokens
        & {
            "credential",
            "credentials",
            "credencial",
            "credenciais",
            "password",
            "secret",
            "segredo",
            "senha",
            "token",
        }
    )
    provider_key = (
        bool(tokens & {"api", "gateway"})
        and bool(tokens & {"chave", "key"})
    ) or "api key" in normalized
    return disclosure and (explicit_secret or provider_key)


def _normalized_text(value: str) -> str:
    return " ".join(
        "".join(
            character
            for character in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(character)
        ).casefold().split()
    )


def _has_prefix(tokens: set[str], *prefixes: str) -> bool:
    return any(
        token.startswith(prefix)
        for token in tokens
        for prefix in prefixes
    )


def _is_manual_catalog_question(tokens: set[str]) -> bool:
    manual_anchor = bool(
        tokens & {"manual", "manufacturer", "fabricante", "troubleshooting"}
    )
    catalog_language = bool(
        tokens
        & {
            "lista",
            "listadas",
            "listed",
            "possiveis",
            "possible",
            "tabela",
            "table",
            "checks",
            "checagens",
        }
    )
    return manual_anchor and catalog_language


def _is_root_cause_request(normalized: str, tokens: set[str]) -> bool:
    if "causa raiz" in normalized or "root cause" in normalized:
        return True
    if _is_manual_catalog_question(tokens):
        return False
    causal_concept = bool(
        tokens
        & {
            "causa",
            "cause",
            "motivo",
            "reason",
            "origem",
            "origin",
            "determinante",
            "determinant",
            "responsavel",
            "underlying",
        }
    ) or _has_prefix(tokens, "motiv", "caus", "diagnost")
    investigative_intent = bool(
        tokens
        & {
            "identifique",
            "identify",
            "determine",
            "explique",
            "explain",
            "qual",
            "what",
            "why",
            "porque",
        }
    ) or "por que" in normalized or "o que" in normalized
    causal_target = bool(
        tokens
        & {
            "falha",
            "failure",
            "defeito",
            "fault",
            "anomalia",
            "anomaly",
            "vibracao",
            "vibration",
        }
    )
    direct_why_question = (
        ("por que" in normalized or bool(tokens & {"why", "porque"}))
        and causal_target
    )
    return direct_why_question or causal_concept and (
        investigative_intent or causal_target
    )


def _is_probability_request(tokens: set[str]) -> bool:
    probability_terms = {
        "probabilidade",
        "probability",
        "likelihood",
        "chance",
        "chances",
        "possibilidade",
        "possibility",
        "odds",
    }
    if tokens & probability_terms:
        return True
    risk_terms = bool(tokens & {"risco", "risk", "percentual", "percentage"})
    failure_terms = bool(
        tokens
        & {
            "falha",
            "failure",
            "parada",
            "stop",
            "quebrar",
            "breakdown",
        }
    )
    return risk_terms and (failure_terms or "%" in tokens)


def _is_remaining_life_request(normalized: str, tokens: set[str]) -> bool:
    if "rul" in tokens or "remaining useful life" in normalized:
        return True
    remaining = bool(
        tokens & {"restante", "remanescente", "remaining", "left"}
    )
    life = bool(
        tokens & {"vida", "life", "durabilidade", "durability"}
    )
    time_question = bool(
        tokens & {"quanto", "quantas", "when", "quando", "hours", "horas"}
    )
    future_failure = _has_prefix(
        tokens, "durar", "falh", "quebr", "parar", "fail", "break"
    )
    return (remaining and life) or (time_question and future_failure)


def _is_execution_request(
    normalized: str, ordered_tokens: tuple[str, ...]
) -> bool:
    tokens = set(ordered_tokens)
    passive_command = any(
        phrase in normalized
        for phrase in (
            "seja executada",
            "seja executado",
            "deve ser realizada",
            "deve ser realizado",
            "precisa ser feita",
            "must be performed",
        )
    )
    command_index = 0
    if ordered_tokens[:2] == ("por", "favor"):
        command_index = 2
    elif ordered_tokens[:2] in {("can", "you"), ("could", "you")}:
        command_index = 2
    elif ordered_tokens and ordered_tokens[0] in {
        "please",
        "pode",
        "poderia",
    }:
        command_index = 1
    command = (
        ordered_tokens[command_index]
        if command_index < len(ordered_tokens)
        else ""
    )
    intervention_commands = {
        "abra",
        "aplique",
        "troque",
        "substitua",
        "desligue",
        "remova",
        "lubrifique",
        "aperte",
        "providencie",
        "conserte",
        "repare",
        "repair",
        "restart",
        "replace",
        "disconnect",
        "remove",
        "apply",
        "tighten",
    }
    generic_commands = {"faca", "execute", "realize", "perform"}
    intervention_targets = {
        "manutencao",
        "maintenance",
        "troca",
        "substituicao",
        "replacement",
        "reparo",
        "repair",
        "motor",
        "equipamento",
        "equipment",
        "rolamento",
        "bearing",
        "terminal",
        "diagnostico",
        "diagnosis",
    }
    imperative = command in intervention_commands or (
        command in generic_commands and bool(tokens & intervention_targets)
    )
    return passive_command or imperative
