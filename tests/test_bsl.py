"""Tests for 1C:Enterprise BSL extractor."""
from __future__ import annotations
from pathlib import Path
import pytest
from graphify.extract import extract_bsl

FIXTURES = Path(__file__).parent / "fixtures"


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def _ids(r):
    return {n["id"] for n in r["nodes"]}


def _relations(r):
    return {e["relation"] for e in r["edges"]}


def _calls(r):
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "calls"
    }


def _contains_edges(r):
    """Returns set of (source_label, target_label) for contains edges."""
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "contains"
    }


# ── Common module (configuration root) ───────────────────────────────────────


class TestCommonModule:
    @pytest.fixture()
    def result(self):
        return extract_bsl(
            FIXTURES / "1c" / "CommonModules" / "ТестовыйМодуль1" / "Ext" / "Module.bsl"
        )

    def test_no_error(self, result):
        assert "error" not in result

    def test_finds_functions(self, result):
        labels = _labels(result)
        assert "МетодОбщегоМодуля()" in labels
        assert "ПриватныйМетодОбщегоМодуля()" in labels

    def test_metadata_object_node(self, result):
        labels = _labels(result)
        assert "ОбщийМодуль.ТестовыйМодуль1" in labels

    def test_metadata_root_node(self, result):
        # Configuration.xml exists at 1c/ root
        labels = _labels(result)
        assert any("Конфигурация." in l for l in labels)

    def test_contains_hierarchy(self, result):
        edges = _contains_edges(result)
        assert any("ОбщийМодуль.ТестовыйМодуль1" in src and "Module.bsl" in tgt
                    for src, tgt in edges)

    def test_contains_root_to_object(self, result):
        edges = _contains_edges(result)
        assert any("Конфигурация." in src and "ОбщийМодуль.ТестовыйМодуль1" in tgt
                    for src, tgt in edges)


# ── Record set module ────────────────────────────────────────────────────────


class TestRecordSetModule:
    @pytest.fixture()
    def result(self):
        return extract_bsl(
            FIXTURES / "1c" / "InformationRegisters" / "РегистрСведений1" / "Ext" / "RecordSetModule.bsl"
        )

    def test_no_error(self, result):
        assert "error" not in result

    def test_finds_procedure(self, result):
        labels = _labels(result)
        assert "ПРиветИзМодуляНабораЗаписей()" in labels

    def test_metadata_object(self, result):
        labels = _labels(result)
        assert "РегистрСведений.РегистрСведений1" in labels


# ── Constants ────────────────────────────────────────────────────────────────


class TestConstantModules:
    def test_manager_module(self):
        result = extract_bsl(
            FIXTURES / "1c" / "Constants" / "Константа1" / "Ext" / "ManagerModule.bsl"
        )
        assert "error" not in result
        labels = _labels(result)
        assert "Константа.Константа1" in labels
        assert "ПриветИзМодуляМенеджера()" in labels

    def test_value_manager_module(self):
        result = extract_bsl(
            FIXTURES / "1c" / "Constants" / "Константа1" / "Ext" / "ValueManagerModule.bsl"
        )
        assert "error" not in result
        labels = _labels(result)
        assert "Константа.Константа1" in labels


# ── Form module ──────────────────────────────────────────────────────────────


class TestFormModule:
    @pytest.fixture()
    def result(self):
        return extract_bsl(
            FIXTURES / "1c" / "Documents" / "ТестовыйДокумент" / "Forms" / "ФормаДокумента" / "Ext" / "Form" / "Module.bsl"
        )

    def test_no_error(self, result):
        assert "error" not in result

    def test_finds_procedures(self, result):
        labels = _labels(result)
        assert "ПриЗакрытииНаСервере()" in labels
        assert "ПриЗакрытии()" in labels

    def test_metadata_object(self, result):
        labels = _labels(result)
        assert "Документ.ТестовыйДокумент" in labels

    def test_form_node(self, result):
        labels = _labels(result)
        assert any("Документ.ТестовыйДокумент.Форма.ФормаДокумента" in l for l in labels)

    def test_form_contains_file(self, result):
        edges = _contains_edges(result)
        assert any("Форма.ФормаДокумента" in src and "Module.bsl" in tgt
                    for src, tgt in edges)

    def test_object_contains_form(self, result):
        edges = _contains_edges(result)
        assert any("Документ.ТестовыйДокумент" in src and "Форма.ФормаДокумента" in tgt
                    for src, tgt in edges)


# ── HTTP service (constructor calls via new_expression) ──────────────────────


class TestHTTPService:
    @pytest.fixture()
    def result(self):
        return extract_bsl(
            FIXTURES / "1c" / "HTTPServices" / "ТестовыйHTTPСервис" / "Ext" / "Module.bsl"
        )

    def test_no_error(self, result):
        assert "error" not in result

    def test_finds_functions(self, result):
        labels = _labels(result)
        assert "ШаблонURL1МетодGET()" in labels
        assert "ШаблонURL2МетодPOST()" in labels

    def test_metadata_object(self, result):
        labels = _labels(result)
        assert "HTTPСервис.ТестовыйHTTPСервис" in labels

    def test_constructor_calls(self, result):
        # HTTPСервисОтвет is a built-in — appears in raw_calls
        raw = result.get("raw_calls", [])
        assert any("HTTPСервисОтвет" in r["callee"] for r in raw)


# ── Standalone BSL (no metadata) ─────────────────────────────────────────────


class TestStandalone:
    @pytest.fixture()
    def result(self):
        return extract_bsl(FIXTURES / "standalone.bsl")

    def test_no_error(self, result):
        assert "error" not in result

    def test_finds_procedures(self, result):
        labels = _labels(result)
        assert "АвтономнаяПроцедура()" in labels

    def test_finds_functions(self, result):
        labels = _labels(result)
        assert "АвтономнаяФункция()" in labels

    def test_no_metadata_nodes(self, result):
        labels = _labels(result)
        for l in labels:
            assert "Справочник." not in l
            assert "ОбщийМодуль." not in l
            assert "Конфигурация." not in l

    def test_direct_call(self, result):
        # Сообщить is a built-in — appears in raw_calls, not in calls edges
        raw = result.get("raw_calls", [])
        assert any(r["callee"] == "Сообщить" for r in raw)

    def test_local_call_resolves_to_edge(self):
        """When a function calls another function defined in the same file,
        it should produce a calls edge (not just raw_calls)."""
        import tempfile, os
        from pathlib import Path
        code = (
            "Процедура Вызывающая()\n"
            "    Вызываемая()\n"
            "КонецПроцедуры\n\n"
            "Процедура Вызываемая()\n"
            "КонецПроцедуры\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".bsl", mode="w", encoding="utf-8",
                                         delete=False, dir=tempfile.gettempdir()) as f:
            f.write(code)
            tmp = f.name
        try:
            r = extract_bsl(Path(tmp))
            calls = _calls(r)
            assert any("Вызываемая" in tgt for _, tgt in calls), f"Expected Вызываемая in calls, got {calls}"
        finally:
            os.unlink(tmp)


# ── Extension ────────────────────────────────────────────────────────────────


class TestExtension:
    @pytest.fixture()
    def result(self):
        return extract_bsl(
            FIXTURES / "1c-ext" / "МоеРасширение" / "CommonModules" / "РасшМодуль1" / "Ext" / "Module.bsl"
        )

    def test_no_error(self, result):
        assert "error" not in result

    def test_extension_root(self, result):
        labels = _labels(result)
        assert "Расширение.МоеРасширение" in labels

    def test_metadata_object(self, result):
        labels = _labels(result)
        assert "ОбщийМодуль.РасшМодуль1" in labels

    def test_finds_procedure(self, result):
        labels = _labels(result)
        assert "РасшМетод()" in labels

    def test_extension_contains_object(self, result):
        edges = _contains_edges(result)
        assert any("Расширение.МоеРасширение" in src and "ОбщийМодуль.РасшМодуль1" in tgt
                    for src, tgt in edges)


# ── External processor ───────────────────────────────────────────────────────


class TestExternalProcessor:
    @pytest.fixture()
    def result(self):
        return extract_bsl(
            FIXTURES / "1c-epf" / "МояОбработка" / "МояОбработка" / "Ext" / "ObjectModule.bsl"
        )

    def test_no_error(self, result):
        assert "error" not in result

    def test_processor_root(self, result):
        labels = _labels(result)
        assert "Обработка.МояОбработка" in labels

    def test_finds_procedure(self, result):
        labels = _labels(result)
        assert "ОбработкаДанных()" in labels

    def test_constructor_call(self, result):
        # Массив is a built-in — appears in raw_calls
        raw = result.get("raw_calls", [])
        assert any("Массив" in r["callee"] for r in raw)
