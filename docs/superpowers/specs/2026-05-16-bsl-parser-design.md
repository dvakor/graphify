# BSL Parser Design

Add 1C:Enterprise BSL (.bsl) support to graphify. Extract procedures, functions, call relationships, and metadata objects from file-based configuration dumps.

## Scope

### In scope (v1)

- Parse `.bsl` files via tree-sitter-bsl v0.1.6
- Extract procedures, functions, and `calls` edges
- Detect metadata objects (Справочник, Документ, etc.) from file path
- Detect metadata root (Конфигурация, Расширение, Обработка, Отчет) from XML files
- Represent forms as nested metadata nodes
- Multi-root support (main config + extensions + external processors)

### Out of scope

- `.os` files (OneScript) — skip entirely
- SDBL query parsing — deferred to v2 (requires tree-sitter-bsl v0.1.7+)
- Metadata attributes, tabular sections, dimensions — future work
- Multi-line query concatenation (`+`, `|`)

## Dependency

`tree-sitter-bsl==0.1.6` — already added via `uv add tree-sitter-bsl`.

## BSL AST Structure

tree-sitter-bsl produces:

```
procedure_definition
    PROCEDURE_KEYWORD [Процедура]
    identifier [Имя]
    parameters
    <statements as direct children>     ← no body wrapper
    ENDPROCEDURE_KEYWORD [КонецПроцедуры]

function_definition
    FUNCTION_KEYWORD [Функция]
    identifier [Имя]
    parameters
    <statements as direct children>
    ENDFUNCTION_KEYWORD [КонецФункции]

method_call
    identifier [ИмяМетода]              ← field "name"
    arguments

call_expression                         ← chain calls: Объект.Метод()
    access
        identifier [Объект]
    .
    method_call
        identifier [Метод]
        arguments
```

Key difference from other languages: **no body node**. Statements are direct children of procedure/function definitions.

## Implementation

### 1. `_BSL_CONFIG` (in `extract.py`)

```python
_BSL_CONFIG = LanguageConfig(
    ts_module="tree_sitter_bsl",
    class_types=frozenset(),
    function_types=frozenset({"procedure_definition", "function_definition"}),
    call_types=frozenset({"method_call", "new_expression"}),  # new_expression: Новый Запрос()
    call_function_field="name",
    function_boundary_types=frozenset({"procedure_definition", "function_definition"}),
    import_types=frozenset(),
    name_field="name",
    name_fallback_child_types=("identifier",),
    function_label_parens=True,
)
```

`new_expression` handles constructor calls like `Новый HTTPСервисОтвет(200)`. In `walk_calls`, the BSL block extracts the type name from the first `identifier` child.

### 2. Flat-body fix (in `_extract_generic`)

After `_find_body()`, if body is `None` and the node type is in `config.function_types`, use the node itself as body. This is a universal fix, not BSL-specific — applies to any language where function bodies are flat. BSL is currently the only language triggering this path.

**Important:** Since `body` IS the function node itself, passing it directly to `walk_calls` would hit the `function_boundary_types` check and return immediately. Instead, when the body node type is in `function_boundary_types`, iterate its children:

```python
for func_nid, body_node in function_bodies:
    if body_node.type in config.function_boundary_types:
        for child in body_node.children:
            walk_calls(child, func_nid)
    else:
        walk_calls(body_node, func_nid)
```

For normal body nodes (block, statement_block, etc.), pass body_node directly as before.

Location: in the body-detection logic within `_extract_generic`, after the existing `_find_body()` call.

### 3. BSL block in `walk_calls` (in `_extract_generic`)

Inside the per-language dispatch in `walk_calls`, add a block for `tree_sitter_bsl`:

```python
elif config.ts_module == "tree_sitter_bsl":
    if node.type == "method_call":
        name_node = node.child_by_field_name("name")
        if name_node:
            callee_name = _read_text(name_node, source)
        # Determine is_member_call: method_call inside call_expression
        if node.parent and node.parent.type == "call_expression":
            is_member_call = True
    elif node.type == "new_expression":
        # Новый HTTPСервисОтвет(200) → callee = HTTPСервисОтвет
        for child in node.children:
            if child.type == "identifier":
                callee_name = _read_text(child, source)
                break
```

### 4. `extract_bsl()` entry point (in `extract.py`)

```python
def extract_bsl(path: Path) -> dict:
    result = _extract_generic(path, _BSL_CONFIG)
    if "error" in result:
        return result
    _enrich_bsl_metadata_from_path(path, result)
    return result
```

### 5. `_enrich_bsl_metadata_from_path()` (in `extract.py`)

Determines the metadata root and object from the file path and nearby XML files.

#### Step 1: Find metadata folder

Walk `path.parts` looking for a recognized top-level metadata folder:

```python
_METADATA_FOLDERS = {
    "Catalogs": "Справочник",
    "Documents": "Документ",
    "InformationRegisters": "РегистрСведений",
    "AccumulationRegisters": "РегистрНакопления",
    "Reports": "Отчет",
    "DataProcessors": "Обработка",
    "Enums": "Перечисление",
    "ChartsOfCharacteristicTypes": "ПланВидовХарактеристик",
    "ChartsOfAccounts": "ПланСчетов",
    "BusinessProcesses": "БизнесПроцесс",
    "Tasks": "Задача",
    "ExchangePlans": "ПланОбмена",
    "Constants": "Константа",
    "CommonModules": "ОбщийМодуль",
    "CommonForms": "ОбщаяФорма",
    "HTTPServices": "HTTPСервис",
    "WebServices": "WebService",
    "WSReferences": "WSСсылка",
    "Subsystems": "Подсистема",
    "EventSubscriptions": "ПодпискаНаСобытие",
    "ScheduledJobs": "РегламентноеЗадание",
    "Roles": "Роль",
    "FilterCriteria": "КритерийОтбора",
    "SettingsStorages": "ХранилищеНастроек",
    "FunctionalOptions": "ФункциональнаяОпция",
    "FunctionalOptionsParameters": "ПараметрФункциональнойОпции",
    "DefinedTypes": "ОпределяемыйТип",
    "CommandGroups": "ГруппаКоманд",
    "CommonAttributes": "ОбщийРеквизит",
    "DocumentJournals": "ЖурналДокументов",
    "DocumentNumerators": "НумераторДокументов",
    "Sequences": "Последовательность",
    "ExternalDataSources": "ВнешнийИсточникДанных",
    "SessionParameters": "ПараметрСеанса",
    "CommonCommands": "ОбщаяКоманда",
    "CommonPictures": "ОбщаяКартинка",
    "CommonTemplates": "ОбщийМакет",
    "Interfaces": "Интерфейс",
    "Languages": "Язык",
}
```

If no recognized folder found — file has no metadata, return without enrichment.

#### Step 2: Detect metadata root

From the position of the recognized folder, walk up **max 2 directory levels** and look for:

1. `Configuration.xml` — read `<Properties><Name>` and detect type:
   - Root tag contains `<Configuration>` with `parent` attribute or path contains `/EXT/` → `Расширение.<Name>`
   - Otherwise → `Конфигурация.<Name>`
2. `<FolderName>.xml` where root tag is `ExternalDataProcessor` → `Обработка.<Name>`
3. `<FolderName>.xml` where root tag is `ExternalReport` → `Отчет.<Name>`

XML parsing via `xml.etree.ElementTree`. **All 1C:Enterprise XML files use the namespace `http://v8.1c.ru/8.3/MDClasses`**. Before querying, strip namespaces from all element tags:

```python
def _strip_xml_namespaces(root):
    for elem in root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]
```

After stripping, `find("Properties/Name")` works. Only `<Properties><Name>` is read, minimal overhead.

If no XML found within 2 levels — file has no metadata root, proceed with object-only enrichment.

#### Step 3: Determine module type

From the filename:

| Filename | Module type label |
|----------|------------------|
| `Module.bsl` (outside Forms/) | (none for common modules) |
| `ObjectModule.bsl` | МодульОбъекта |
| `ManagerModule.bsl` | МодульМенеджера |
| `RecordSetModule.bsl` | МодульНабораЗаписей |
| `ValueManagerModule.bsl` | МодульМенеджераЗначений |
| `Module.bsl` (inside Forms/) | МодульФормы |

#### Step 4: Build graph nodes

Produce metadata nodes and `contains` edges. Insert them at the beginning of the nodes list so the hierarchy is clear.

**Object without form:**
```
metadata_root (e.g. "Конфигурация.CRM")
  └── contains → object_node (e.g. "ОбщийМодуль.такРаботаС...")
        └── contains → file_node (already exists from _extract_generic)
```

**Object with form:**
```
metadata_root (e.g. "Конфигурация.CRM")
  └── contains → object_node (e.g. "Справочник.ШаблоныАнкет")
        └── contains → form_node (e.g. "Справочник.ШаблоныАнкет.Форма.CRM_ФормаЭлемента")
              └── contains → file_node
```

**Form detection:** if `Forms` appears in path parts between the metadata folder and the module file, extract the form name from the folder after `Forms/`.

Node IDs are generated via `_make_id()` using the full dotted name (e.g. `_make_id("Конфигурация", "CRM")` for the root, `_make_id("Справочник", "ШаблоныАнкет")` for the object).

### 6. Registration

**`detect.py`:**
```python
# Add to CODE_EXTENSIONS
'.bsl',
```

**`extract.py` `_DISPATCH`:**
```python
".bsl": extract_bsl,
```

**`watch.py`:**
```python
# Add to _WATCHED_EXTENSIONS
'.bsl',
```

## Tests

File: `tests/test_bsl.py`

Fixtures copied from `/Users/d.korolev/Work/My/Projects/ProjectContext/packages/scanner/tests/fixtures/bsl_real/` into `tests/fixtures/1c/`.

| Fixture path | Assertions |
|-------------|-----------|
| `1c/CommonModules/ТестовыйМодуль1/Ext/Module.bsl` | 2 functions extracted, `calls` edges, metadata node `ОбщийМодуль.ТестовыйМодуль1`, root node from `Configuration.xml` |
| `1c/InformationRegisters/РегистрСведений1/Ext/RecordSetModule.bsl` | 1 procedure, metadata `РегистрСведений.РегистрСведений1` |
| `1c/Constants/Константа1/Ext/ManagerModule.bsl` | metadata `Константа.Константа1`, module type МодульМенеджера |
| `1c/Constants/Константа1/Ext/ValueManagerModule.bsl` | metadata `Константа.Константа1`, module type МодульМенеджераЗначений |
| `1c/Documents/ТестовыйДокумент/Forms/ФормаДокумента/Ext/Form/Module.bsl` | metadata `Документ.ТестовыйДокумент.Форма.ФормаДокумента`, 2 procedures |
| `1c/HTTPServices/ТестовыйHTTPСервис/Ext/Module.bsl` | metadata `HTTPСервис.ТестовыйHTTPСервис`, 2 functions, `calls` edge to `HTTPСервисОтвет` via `new_expression` |
| Standalone `.bsl` (no folder structure) | procedures only, no metadata nodes |
| Extension fixture (synthetic Configuration.xml with parent attribute) | root node `Расширение.<Name>` |
| External processor fixture (synthetic `<Name>.xml` + `Ext/ObjectModule.bsl`) | root node `Обработка.<Name>` |

Test structure follows the pattern in `tests/test_languages.py`.

## Graph Example

```
Конфигурация.CRM
  ├── ОбщийМодуль.ТестовыйМодуль1
  │     └── Module.bsl
  │           ├── МетодОбщегоМодуля()  ──calls──→ Сообщить
  │           └── ПриватныйМетодОбщегоМодуля()
  ├── РегистрСведений.РегистрСведений1
  │     └── RecordSetModule.bsl
  │           └── ПРиветИзМодуляНабораЗаписей()
  ├── Константа.Константа1
  │     └── ManagerModule.bsl
  │           └── ПриветИзМодуляМенеджера()
  ├── Документ.ТестовыйДокумент
  │     └── Документ.ТестовыйДокумент.Форма.ФормаДокумента
  │           └── Module.bsl
  │                 ├── ПриЗакрытииНаСервере()
  │                 └── ПриЗакрытии()
  └── HTTPСервис.ТестовыйHTTPСервис
        └── Module.bsl
              ├── ШаблонURL1МетодGET()  ──calls──→ HTTPСервисОтвет
              └── ШаблонURL2МетодPOST() ──calls──→ HTTPСервисОтвет
```

## Future Work

- **SDBL parsing** — when tree-sitter-bsl v0.1.7 is on PyPI, parse embedded queries (`ВЫБРАТЬ...`) for `reads_from` / `joins` edges
- **Metadata enrichment** — parse `.xml` files (Catalogs, etc.) for attributes, tabular sections, type references
- **`.os` support** — OneScript files (same grammar, no metadata structure)
- **Cross-file call resolution** — resolve calls across modules via metadata object names (e.g. `такРаботаС.Метод()` → edge to the target module's function)
