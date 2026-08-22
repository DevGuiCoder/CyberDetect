import csv
import io
import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


MULTICLASS_LABELS = ("SEGURO", "SUSPEITO", "GOLPE")
BINARY_LABELS = ("LEGITIMO", "GOLPE")

TEXT_FIELDS = (
    "text",
    "texto",
    "conteudo",
    "content",
    "mensagem",
    "message",
    "ocr_text",
    "body",
)
GROUND_TRUTH_FIELDS = (
    "ground_truth",
    "classe_real",
    "classificacao_real",
    "label",
    "classe",
    "class",
    "target",
)
ID_FIELDS = ("id", "sample_id", "uid", "codigo")
SOURCE_FIELDS = ("source", "origem", "fonte")


@dataclass
class DatasetSample:
    id: str
    text: str
    ground_truth: str
    source: str
    category: str = ""
    language: str = "pt-BR"
    source_dataset: str = ""
    translated: bool = False
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_label(value: Any, binary: bool = False) -> str:
    folded = str(value or "").strip().upper()
    folded = folded.replace("Í", "I").replace("Ã", "A").replace("Ç", "C")
    folded = folded.replace(" ", "_").replace("-", "_")
    aliases = {
        "SAFE": "SEGURO",
        "NORMAL": "SEGURO",
        "LEGITIMO": "LEGITIMO" if binary else "SEGURO",
        "LEGITIMA": "LEGITIMO" if binary else "SEGURO",
        "HAM": "LEGITIMO" if binary else "SEGURO",
        "SUSPEITA": "SUSPEITO",
        "SUSPICIOUS": "SUSPEITO",
        "ALERTA": "SUSPEITO",
        "SCAM": "GOLPE",
        "FRAUDE": "GOLPE",
        "FRAUD": "GOLPE",
        "PHISHING": "GOLPE",
        "MALICIOUS": "GOLPE",
    }
    label = aliases.get(folded, folded)
    valid = BINARY_LABELS if binary else MULTICLASS_LABELS
    if label not in valid:
        raise ValueError(f"Classe real invalida: {value!r}. Use {', '.join(valid)}.")
    return label


def _value(row: dict[str, Any], keys: Iterable[str], default: Any = "") -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for key in keys:
        if key in lowered and lowered[key] not in (None, ""):
            return lowered[key]
    return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "sim", "yes", "y"}


def _normalize_row(row: dict[str, Any], index: int, dataset_name: str, binary: bool = False) -> DatasetSample:
    text = str(_value(row, TEXT_FIELDS)).strip()
    if not text:
        raise ValueError("Amostra sem conteudo textual.")

    ground_truth = normalize_label(_value(row, GROUND_TRUTH_FIELDS), binary=binary)
    sample_id = str(_value(row, ID_FIELDS, f"{dataset_name}-{index:06d}")).strip()
    source = str(_value(row, SOURCE_FIELDS, dataset_name)).strip() or dataset_name
    metadata = {
        str(key): value
        for key, value in row.items()
        if str(key).strip().lower()
        not in set(TEXT_FIELDS + GROUND_TRUTH_FIELDS + ID_FIELDS + SOURCE_FIELDS)
    }

    return DatasetSample(
        id=sample_id,
        text=text,
        ground_truth=ground_truth,
        source=source,
        category=str(_value(row, ("category", "categoria", "tipo"), "") or "").strip(),
        language=str(_value(row, ("language", "idioma", "lang"), "pt-BR") or "pt-BR").strip(),
        source_dataset=str(_value(row, ("source_dataset", "dataset_original", "dataset"), dataset_name) or "").strip(),
        translated=_bool(_value(row, ("translated", "traduzido", "is_translated"), False)),
        notes=str(_value(row, ("notes", "observacoes", "observacao"), "") or "").strip(),
        metadata=metadata,
    )


def parse_dataset_content(
    filename: str,
    content: str,
    dataset_name: str = "",
    binary: bool = False,
) -> tuple[list[DatasetSample], list[str]]:
    extension = Path(filename or "").suffix.lower()
    name = dataset_name.strip() or Path(filename or "dataset").stem or "dataset"
    rows: list[dict[str, Any]] = []

    if extension == ".csv":
        reader = csv.DictReader(io.StringIO(content or ""))
        rows = [dict(row) for row in reader]
    elif extension == ".jsonl":
        for line_number, line in enumerate((content or "").splitlines(), 1):
            if line.strip():
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(item)
                    else:
                        rows.append({"_invalid": item})
                except json.JSONDecodeError as exc:
                    rows.append({"_error": f"Linha {line_number}: {exc}"})
    elif extension == ".json":
        data = json.loads(content or "[]")
        if isinstance(data, dict):
            candidates = data.get("samples") or data.get("data") or data.get("items") or []
            rows = candidates if isinstance(candidates, list) else []
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
    else:
        raise ValueError("Formato nao suportado. Use CSV, JSON ou JSONL.")

    samples: list[DatasetSample] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"Linha {index}: registro nao e objeto.")
            continue
        if row.get("_error"):
            errors.append(str(row["_error"]))
            continue
        try:
            sample = _normalize_row(row, index, name, binary=binary)
            if sample.id in seen_ids:
                sample.id = f"{sample.id}-{index:06d}"
            seen_ids.add(sample.id)
            samples.append(sample)
        except Exception as exc:
            errors.append(f"Linha {index}: {exc}")

    return samples, errors


def select_samples(
    samples: list[dict[str, Any]],
    limit: int | None = None,
    seed: int | None = None,
    category: str = "",
    language: str = "",
) -> list[dict[str, Any]]:
    selected = list(samples)
    if category:
        selected = [item for item in selected if str(item.get("category") or "").lower() == category.lower()]
    if language:
        selected = [item for item in selected if str(item.get("language") or "").lower() == language.lower()]

    if seed is not None:
        rng = random.Random(seed)
        rng.shuffle(selected)

    if limit and limit > 0:
        selected = selected[:limit]
    return selected
