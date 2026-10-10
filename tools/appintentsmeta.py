#!/usr/bin/env python3
"""Linux replacement for Xcode 27's App Intents build steps.

Xcode runs two tools after linking an app or app extension that uses App Intents:

  appintentsmetadataprocessor   -> Metadata.appintents/{extract.actionsdata,version.json}
  appintentsnltrainingprocessor -> Metadata.appintents/{root.ssu.yaml,nlu/nlu.lzfse,nlu/<md5>.version}

This tool produces the same files from the same inputs: the `.swiftconstvalues` files that
swiftc writes with `-emit-const-values -const-gather-protocols-list`, the module name, the
bundle identifier, the Info.plist, and Xcode's SiriSSUKitModel resources (prefix/ and
standardAppShortcutNegatives/ YAML lists). Python standard library only.

Usage (mirrors Xcode's arguments):
  appintentsmeta.py --module-name M --bundle-identifier B --output APP_OR_APPEX_DIR \
      --swift-const-vals-list LIST | --const-values FILE... \
      [--binary-file BIN] [--deployment-target 18.0] [--xcode-version 27A266a] \
      [--info-plist APP/Info.plist] [--ssu-resources DIR] [--timestamp UNIX_SECONDS]

Constructs that are not reproduced exactly raise MetadataError naming the construct; the
tool never writes guessed metadata.
"""
import argparse
import hashlib
import json
import os
import plistlib
import re
import struct
import sys
import time


class MetadataError(Exception):
    """Input uses an App Intents construct this tool does not reproduce, or is invalid."""


# ---------------------------------------------------------------------------
# Const values helpers

def split_generic(name):
    """'A.B<C, D<E>>' -> ('A.B', ['C', 'D<E>']); non-generic names -> (name, [])."""
    lt = name.find('<')
    if lt < 0 or not name.endswith('>'):
        return name, []
    args, depth, cur = [], 0, ''
    for ch in name[lt + 1:-1]:
        if ch == '<':
            depth += 1
        elif ch == '>':
            depth -= 1
        if ch == ',' and depth == 0:
            args.append(cur.strip())
            cur = ''
        else:
            cur += ch
    args.append(cur.strip())
    return name[:lt], args


def short_name(type_name):
    return type_name.rsplit('.', 1)[-1]


def args_of(value):
    """InitCall value -> {label: argument}."""
    return {a['label']: a for a in value.get('arguments', [])}


def is_nil(arg):
    return arg is None or arg.get('valueKind') in ('NilLiteral', 'Runtime')


def literal(arg, what):
    if arg.get('valueKind') != 'RawLiteral':
        raise MetadataError(f'{what}: expected a literal, got {arg.get("valueKind")}')
    return arg['value']


def string_template(node, what):
    """RawLiteral or InterpolatedStringLiteral -> 'text ${name} text' (App Intents key form)."""
    kind = node.get('valueKind')
    if kind == 'RawLiteral':
        return node['value']
    if kind == 'InterpolatedStringLiteral':
        out = ''
        for seg in node['value']['segments']:
            sk = seg['valueKind']
            if sk == 'RawLiteral':
                out += seg['value']
            elif sk == 'Enum':
                out += '${' + seg['value']['name'] + '}'
            elif sk == 'KeyPath':
                out += '${' + seg['value']['path'].lstrip('$') + '}'
            else:
                raise MetadataError(f'{what}: unsupported interpolation segment {sk}')
        return out
    raise MetadataError(f'{what}: expected a string literal, got {kind}')


def localized(key):
    return {'alternatives': [], 'key': key}


def localized_node(node, what):
    kind = node.get('valueKind')
    if kind in ('RawLiteral', 'InterpolatedStringLiteral'):
        return localized(string_template(node, what))
    if kind == 'InitCall' and node['value']['type'] == 'Foundation.LocalizedStringResource':
        a = args_of(node['value'])
        extra = [k for k, v in a.items() if k != '' and not is_nil(v)]
        if extra:
            raise MetadataError(f'{what}: LocalizedStringResource arguments {extra} are not supported')
        return localized(string_template(a[''], what))
    raise MetadataError(f'{what}: unsupported localized string form {kind}')


WILDCARD = {'LNPlatformNameWildcard': {'introducedVersion': '*'}}
PLATFORM_KEYS = {'iOS': 'LNPlatformNameIOS'}


def availability(entry):
    out = dict(WILDCARD)
    for attr in entry.get('availabilityAttributes', []):
        if attr.get('isUnavailable') or attr.get('isDeprecated') or set(attr) - {
                'platform', 'introducedVersion', 'isUnavailable', 'isDeprecated'}:
            raise MetadataError(f'{entry["typeName"]}: unsupported availability attribute {attr}')
        key = PLATFORM_KEYS.get(attr['platform'])
        if key is None:
            raise MetadataError(f'{entry["typeName"]}: unsupported availability platform {attr["platform"]}')
        out[key] = {'introducedVersion': attr['introducedVersion']}
    return out


VISIBLE = {'assistantOnly': False, 'isDiscoverable': True}


# ---------------------------------------------------------------------------
# Module model

class Module:
    def __init__(self, entries, module_name):
        foreign = [e['typeName'] for e in entries if not e['typeName'].startswith(module_name + '.')]
        if foreign:
            raise MetadataError(f'const values are not from module {module_name}: {foreign[:3]}')
        self.entries = entries
        self.by_name = {e['typeName']: e for e in entries}

    def conforms(self, entry, proto):
        return proto in entry.get('conformances', [])

    def of(self, proto):
        return [e for e in self.entries if self.conforms(e, proto)]

    def entry(self, type_name):
        return self.by_name.get(type_name)

    def is_entity(self, type_name):
        e = self.entry(type_name)
        return e is not None and self.conforms(e, 'AppIntents.AppEntity')

    def is_enum(self, type_name):
        e = self.entry(type_name)
        return e is not None and self.conforms(e, 'AppIntents.AppEnum')


def prop(entry, label):
    for p in entry.get('properties', []):
        if p['label'] == label:
            return p
    return None


def alias(entry, name):
    for a in entry.get('associatedTypeAliases', []):
        if a['typeAliasName'] == name:
            return a
    return None


# ---------------------------------------------------------------------------
# Value types (LNValueType)

PRIMITIVES = {
    'Swift.String': 0, 'Swift.Bool': 1, 'Swift.Int': 2, 'Swift.Double': 7,
    'Foundation.Date': 8, 'Foundation.DateComponents': 9, 'Foundation.URL': 11,
    'Foundation.AttributedString': 12,
}
INTENT_TYPES = {'AppIntents.IntentPerson': 3, 'AppIntents.IntentFile': 12, 'AppIntents.IntentCurrencyAmount': 14}
MEASUREMENT_UNITS = {'Foundation.UnitLength': 1}


def prim(n):
    return {'primitive': {'wrapper': {'typeIdentifier': n}}}


def resolvable(vt):
    return {'kindValue': 0, 'valueType': vt}


def array_of(vt):
    return {'array': {'wrapper': {'capabilities': 3, 'memberValueType': vt}}}


# Xcode emits these in hash-table order, which differs from run to run; this order is fixed.
RESOLVABLE = {
    0: [prim(0), prim(2), array_of(prim(2))],
    1: [prim(1)],
    2: [prim(2), prim(7), prim(0)],
    7: [prim(7), prim(2), prim(0)],
    8: [prim(8)],
    9: [prim(9)],
    11: [prim(0), prim(11)],
    12: [prim(12), prim(0)],
}


def unwrap_optional(type_name):
    base, args = split_generic(type_name)
    if base == 'Swift.Optional':
        return args[0], True
    return type_name, False


class ValueType:
    def __init__(self, module, type_name, what):
        self.module = module
        self.what = what
        self.type_name = type_name
        base, args = split_generic(type_name)
        self.kind = None
        self.element = None
        if base == 'Swift.Array':
            self.kind = 'array'
            self.element = ValueType(module, args[0], what)
            if self.element.kind == 'array':
                raise MetadataError(f'{what}: nested arrays are not supported')
            self.json = array_of(self.element.json)
        elif type_name in PRIMITIVES:
            self.kind = 'primitive'
            self.id = PRIMITIVES[type_name]
            self.json = prim(self.id)
        elif type_name in INTENT_TYPES:
            self.kind = 'intents'
            self.id = INTENT_TYPES[type_name]
            self.json = {'intents': {'wrapper': {'typeIdentifier': self.id}}}
        elif base == 'Foundation.Measurement' and args and args[0] in MEASUREMENT_UNITS:
            self.kind = 'measurement'
            self.id = MEASUREMENT_UNITS[args[0]]
            self.json = {'measurement': {'wrapper': {'unitType': self.id}}}
        elif module.is_entity(type_name):
            self.kind = 'entity'
            self.json = {'entity': {'wrapper': {'typeName': short_name(type_name)}}}
        elif module.is_enum(type_name):
            self.kind = 'enum'
            self.json = {'linkEnumeration': {'wrapper': {'identifier': short_name(type_name)}}}
        else:
            raise MetadataError(f'{what}: unsupported value type {type_name}')

    def resolvable_inputs(self):
        if self.kind == 'primitive':
            return [resolvable(v) for v in RESOLVABLE[self.id]]
        if self.kind == 'intents' and self.id == 12:
            return [resolvable(self.json)]
        if self.kind == 'measurement':
            return [resolvable(self.json)]
        return []

    def file_type(self):
        return (self.kind == 'intents' and self.id == 12) or (
            self.kind == 'array' and self.element.kind == 'intents' and self.element.id == 12)


# ---------------------------------------------------------------------------
# UTType member -> identifier, read from the SDK's UTCoreTypes.h ("UTI: public.jpeg").

def load_uttypes(sdk_root):
    path = os.path.join(sdk_root or '', 'System/Library/Frameworks/UniformTypeIdentifiers.framework/Headers/UTCoreTypes.h')
    table = {}
    if not os.path.isfile(path):
        return table
    text = open(path, encoding='utf-8').read()
    for m in re.finditer(r'UTI:\s*(\S+)(?:(?!UT_EXPORT).)*?UT_EXPORT UTType \*const UTType(\w+)', text, re.S):
        table[m.group(2).lower()] = m.group(1)
    return table


# ---------------------------------------------------------------------------
# Parameters

def tsm_pair(key, kind, value):
    return [key, {kind: {'wrapper': value}}]


def default_value_metadata(vt, node, what):
    kind = node['valueKind']
    if vt.kind == 'enum' and kind == 'Enum':
        return tsm_pair('LNValueTypeSpecificMetadataKeyDefaultValue', 'string', enum_case_identifier(vt, node['value']['name']))
    if vt.kind == 'primitive' and kind == 'RawLiteral':
        raw = node['value']
        if vt.id == 0:
            return tsm_pair('LNValueTypeSpecificMetadataKeyDefaultValue', 'string', raw)
        if vt.id == 2:
            return tsm_pair('LNValueTypeSpecificMetadataKeyDefaultValue', 'int', int(raw))
        if vt.id == 1:
            return tsm_pair('LNValueTypeSpecificMetadataKeyDefaultValue', 'int', 1 if raw == 'true' else 0)
    raise MetadataError(f'{what}: unsupported default value {kind} for {vt.type_name}')


def enum_case_identifier(vt, case_name):
    entry = vt.module.entry(vt.type_name)
    for c in entry.get('cases', []):
        if c['name'] == case_name:
            return c.get('rawValue', c['name'])
    raise MetadataError(f'{vt.type_name}: unknown case {case_name}')


def json_number(text):
    v = float(text)
    return int(v) if v.is_integer() else v


def range_metadata(node, what):
    if node.get('valueKind') != 'Tuple':
        raise MetadataError(f'{what}: inclusiveRange must be a literal tuple')
    lo, hi = node['value']
    return (tsm_pair('LNValueTypeMetadataKeyNumberUpperBound', 'double', json_number(literal(hi, what)))
            + tsm_pair('LNValueTypeMetadataKeyNumberLowerBound', 'double', json_number(literal(lo, what)))
            + tsm_pair('LNValueTypeMetadataKeyNumberRangeType', 'int', 0))


CONTROL_STYLES = {'field': 1, 'slider': 2}
KEYBOARD_TYPES = {'default': 0, 'URL': 2}
CAPITALIZATION = {'none': 0}
INPUT_CONNECTION = {'default': 0, 'connectToPreviousIntentResult': 2}


def string_options_metadata(node, what):
    if node.get('valueKind') != 'InitCall':
        raise MetadataError(f'{what}: inputOptions must be a literal initializer')
    out = []
    for label, arg in args_of(node['value']).items():
        if is_nil(arg):
            continue
        if label == 'keyboardType':
            out += tsm_pair('LNValueTypeMetadataKeyStringKeyboardType', 'int', KEYBOARD_TYPES[arg['value']['name']])
        elif label == 'capitalizationType':
            out += tsm_pair('LNValueTypeMetadataKeyStringCapitalizationType', 'int', CAPITALIZATION[arg['value']['name']])
        elif label == 'multiline':
            out += tsm_pair('LNValueTypeMetadataKeyStringMultiline', 'int', 1 if literal(arg, what) == 'true' else 0)
        elif label == 'autocorrect':
            out += tsm_pair('LNValueTypeMetadataKeyStringAutocorrect', 'int', 1 if literal(arg, what) == 'true' else 0)
        else:
            raise MetadataError(f'{what}: unsupported inputOptions argument {label}')
    return out


def parameter(module, owner, prop_entry, uttypes):
    name = prop_entry['label'].lstrip('_')
    what = f'{owner["typeName"]}.{name}'
    wrapper_type, wrapper_args = split_generic(prop_entry['type'])
    if wrapper_type != 'AppIntents.IntentParameter':
        raise MetadataError(f'{what}: unsupported property wrapper {wrapper_type}')
    value_type, optional = unwrap_optional(wrapper_args[0])
    vt = ValueType(module, value_type, what)
    if prop_entry.get('valueKind') != 'InitCall':
        raise MetadataError(f'{what}: @Parameter arguments must be compile-time constants')
    a = args_of(prop_entry['value'])
    p = {
        'capabilities': 0,
        'dynamicOptionsSupport': 0,
        'inputConnectionBehavior': 0,
        'isInput': False,
        'isOptional': optional,
        'name': name,
        'resolvableInputTypes': vt.resolvable_inputs(),
        'title': localized_node(a['title'], what),
        'typeSpecificMetadata': [],
        'valueType': vt.json,
    }
    tsm = []
    options_provider = False
    for label, arg in a.items():
        if label in ('title', 'requestValueDialog', 'requestDisambiguationDialog', 'supportedValues') or is_nil(arg):
            continue
        if label == 'description':
            p['parameterDescription'] = localized_node(arg, what)
        elif label == 'default':
            p['capabilities'] |= 1
            tsm += default_value_metadata(vt, arg, what)
        elif label == 'inclusiveRange':
            tsm += range_metadata(arg, what)
        elif label == 'controlStyle':
            tsm += tsm_pair('LNValueTypeMetadataKeyNumberControlStyle', 'int', CONTROL_STYLES[arg['value']['name']])
        elif label == 'inputOptions':
            tsm += string_options_metadata(arg, what)
        elif label == 'inputConnectionBehavior':
            behavior = INPUT_CONNECTION.get(arg['value']['name']) if arg['valueKind'] == 'Enum' else None
            if behavior is None:
                raise MetadataError(f'{what}: unsupported inputConnectionBehavior')
            p['inputConnectionBehavior'] = behavior
            p['isInput'] = behavior == 2
        elif label == 'supportedContentTypes' and vt.file_type():
            if arg['valueKind'] != 'Array':
                raise MetadataError(f'{what}: supportedContentTypes must be an array literal')
            elements = []
            for el in arg['value']:
                member = el['value']['memberLabel'] if el['valueKind'] == 'MemberReference' else None
                uti = uttypes.get((member or '').lower())
                if uti is None:
                    raise MetadataError(f'{what}: unknown UTType member {member} (pass --sdk-root)')
                elements.append({'string': {'wrapper': uti}})
            tsm += ['LNValueTypeMetadataKeyFileSupportedTypes', {'array': {'elements': elements}}]
        elif label == 'optionsProvider':
            provider = module.entry(arg['value']['type']) if arg['valueKind'] == 'InitCall' else None
            if provider is None or not module.conforms(provider, 'AppIntents.DynamicOptionsProvider'):
                raise MetadataError(f'{what}: optionsProvider must initialize a DynamicOptionsProvider of this module')
            p['capabilities'] |= 8
            options_provider = True
        else:
            raise MetadataError(f'{what}: unsupported @Parameter argument {label}')
    if vt.kind == 'measurement':
        tsm = (tsm_pair('LNValueTypeMetadataKeyMeasurementUnitType', 'int', vt.id)
               + tsm_pair('LNValueTypeMetadataKeyMeasurementUnitAdjustsForLocale', 'int', 0) + tsm)
    target = vt.element if vt.kind == 'array' else vt
    string_query = target.kind == 'entity' and module.conforms(
        module.entry(entity_query_type(module, module.entry(target.type_name))), 'AppIntents.EntityStringQuery')
    if options_provider:
        if string_query:
            raise MetadataError(f'{what}: optionsProvider on an entity with an EntityStringQuery is not supported')
        p['dynamicOptionsSupport'] = 1
    elif target.kind == 'entity':
        p['dynamicOptionsSupport'] = 2 if string_query else 1
    p['typeSpecificMetadata'] = tsm
    return p


# ---------------------------------------------------------------------------
# Actions

OUTPUT_FLAGS = {'AppIntents.OpensIntent': 1, 'AppIntents.ShowsSnippetView': 2, 'AppIntents.ProvidesDialog': 4}
IGNORED_RESULT_PROTOCOLS = {'AppIntents.IntentResult', 'AppIntents.ReturnsValue'}
WIDGET_PROTOCOL = 'com.apple.link.systemProtocol.WidgetConfiguration'


def output_metadata(module, entry):
    result = alias(entry, 'PerformResult')
    if result is None:
        raise MetadataError(f'{entry["typeName"]}: no PerformResult in const values')
    if result['substitutedTypeName'] == 'Swift.Never':
        return 8, None
    flags = 0
    for proto in result.get('opaqueTypeProtocolRequirements', []):
        if proto in OUTPUT_FLAGS:
            flags |= OUTPUT_FLAGS[proto]
        elif proto not in IGNORED_RESULT_PROTOCOLS:
            raise MetadataError(f'{entry["typeName"]}: unsupported perform() result protocol {proto}')
    output_type = None
    for req in result.get('opaqueTypeSameTypeRequirements', []):
        if req['typeAliasName'] == 'AppIntents.IntentResult.Value':
            output_type = ValueType(module, req['substitutedTypeName'], entry['typeName'] + '.perform').json
        else:
            raise MetadataError(f'{entry["typeName"]}: unsupported result requirement {req["typeAliasName"]}')
    return flags, output_type


def static_value(entry, label):
    p = prop(entry, label)
    if p is None:
        return None
    if p.get('isStatic') != 'true':
        raise MetadataError(f'{entry["typeName"]}.{label} must be static')
    return p


def bool_value(entry, label, default):
    p = static_value(entry, label)
    if p is None:
        return default, False
    return literal(p, f'{entry["typeName"]}.{label}') == 'true', True


AUTH_POLICIES = {'alwaysAllowed': 0, 'requiresAuthentication': 1, 'requiresLocalDeviceAuthentication': 2}


def description_metadata(entry):
    p = static_value(entry, 'description')
    if p is None:
        return None
    what = entry['typeName'] + '.description'
    if p['valueKind'] in ('RawLiteral', 'InterpolatedStringLiteral'):
        return {'descriptionText': localized_node(p, what), 'searchKeywords': []}
    if p['valueKind'] != 'InitCall' or p['value']['type'] != 'AppIntents.IntentDescription':
        raise MetadataError(f'{what}: unsupported description form')
    a = args_of(p['value'])
    out = {'descriptionText': localized_node(a[''], what), 'searchKeywords': []}
    for label, arg in a.items():
        if label == '' or is_nil(arg):
            continue
        if label == 'categoryName':
            out['categoryName'] = {'title': localized_node(arg, what)}
        elif label == 'searchKeywords':
            out['searchKeywords'] = [localized_node(k, what) for k in arg['value']]
        else:
            raise MetadataError(f'{what}: unsupported IntentDescription argument {label}')
    return out


def parameter_summary(entry):
    p = static_value(entry, 'parameterSummary')
    if p is None:
        return None
    what = entry['typeName'] + '.parameterSummary'
    value = p.get('value') or {}
    if p.get('valueKind') != 'InitCall' or not value.get('type', '').startswith('AppIntents.IntentParameterSummary<'):
        raise MetadataError(f'{what}: only Summary("...") {{ ... }} is supported')
    text, others = None, []
    for arg in value.get('arguments', []):
        kind = arg.get('valueKind')
        if arg['label'] == 'table' and is_nil(arg):
            continue
        if arg['label'] == '' and kind in ('RawLiteral', 'InterpolatedStringLiteral') and text is None:
            text = arg
        elif arg['label'] == '' and kind == 'Builder':
            for member in arg['value']['members']:
                el = member['element']
                if member.get('kind') != 'buildExpression' or el['valueKind'] != 'KeyPath':
                    raise MetadataError(f'{what}: unsupported Summary member {el["valueKind"]}')
                others.append(el['value']['path'].lstrip('$'))
        else:
            raise MetadataError(f'{what}: unsupported Summary argument {arg["label"]!r} ({kind})')
    if text is None:
        raise MetadataError(f'{what}: Summary has no string')
    fmt = string_template(text, what)
    ids = [seg['value']['path'].lstrip('$') for seg in text['value']['segments'] if seg['valueKind'] == 'KeyPath'] \
        if text['valueKind'] == 'InterpolatedStringLiteral' else []
    return {'actionSummary': {'wrapper': {'otherParameterIdentifiers': others,
                                          'summaryString': {'formatString': fmt, 'parameterIdentifiers': ids}}}}


def action(module, entry, uttypes):
    name = entry['typeName']
    widget = module.conforms(entry, 'AppIntents.WidgetConfigurationIntent')
    discoverable, explicit_discoverable = bool_value(entry, 'isDiscoverable', not widget)
    open_app, _ = bool_value(entry, 'openAppWhenRun', False)
    auth = static_value(entry, 'authenticationPolicy')
    flags, output_type = output_metadata(module, entry)
    params = [parameter(module, entry, p, uttypes) for p in entry.get('properties', [])
              if p['label'].startswith('_') and split_generic(p['type'])[0] == 'AppIntents.IntentParameter']
    title = static_value(entry, 'title')
    if title is None:
        raise MetadataError(f'{name}: missing static title')
    out = {
        'assistantDefinedSchemaTraits': [],
        'assistantDefinedSchemas': [],
        'authenticationPolicy': AUTH_POLICIES[auth['value']['name']] if auth else 0,
        'availabilityAnnotations': availability(entry),
        'effectiveBundleIdentifiers': [],
        'fullyQualifiedTypeName': name,
        'identifier': short_name(name),
        'isAuthPolExplicit': auth is not None,
        'isDiscoverable': discoverable,
        'mangledTypeName': entry['mangledTypeName'],
        'mangledTypeNameByBundleIdentifier': {},
        'mangledTypeNameByBundleIdentifierV2': {},
        'mangledTypeNameV2': entry['mangledTypeName'],
        'openAppWhenRun': open_app,
        'outputFlags': flags,
        'parameters': params,
        'presentationStyle': 0,
        'requiredCapabilities': [],
        'supportedModes': 2 if open_app else 1,
        'systemProtocolMetadata': [WIDGET_PROTOCOL, {'empty': {}}] if widget else [],
        'systemProtocolMetadataV2': [WIDGET_PROTOCOL, {'empty': {}}] if widget else [],
        'systemProtocols': [WIDGET_PROTOCOL] if widget else [],
        'title': localized_node(title, name + '.title'),
        'typeSpecificMetadata': [],
        'visibilityMetadata': {'assistantOnly': False,
                               'isDiscoverable': discoverable if explicit_discoverable else True},
    }
    if output_type is not None:
        out['outputType'] = output_type
    desc = description_metadata(entry)
    if desc is not None:
        out['descriptionMetadata'] = desc
    summary = parameter_summary(entry)
    if summary is not None:
        out['actionConfiguration'] = summary
    return out


# ---------------------------------------------------------------------------
# Entities, queries, enums

def display_type_name(entry):
    """typeDisplayRepresentation (or the older typeDisplayName) -> (name, numericFormat)."""
    what = entry['typeName'] + '.typeDisplayRepresentation'
    p = prop(entry, 'typeDisplayRepresentation')
    if p is not None and p.get('valueKind') != 'Runtime':
        if p['valueKind'] == 'InitCall':
            a = args_of(p['value'])
            numeric = a.get('numericFormat')
            return (localized_node(a['name'], what),
                    None if is_nil(numeric) else localized_node(numeric, what))
        return localized_node(p, what), None
    p = prop(entry, 'typeDisplayName')
    if p is not None and p.get('valueKind') != 'Runtime':
        return localized_node(p, entry['typeName'] + '.typeDisplayName'), None
    raise MetadataError(f'{what} must be static, have a compile-time constant value, and cannot be computed or dynamic')


def entity_query_type(module, entry):
    a = alias(entry, 'DefaultQuery')
    if a is None:
        raise MetadataError(f'{entry["typeName"]}: no DefaultQuery in const values')
    return a['substitutedTypeName']


def entity_property(module, entry, p):
    name = p['label'].lstrip('_')
    what = f'{entry["typeName"]}.{name}'
    value_type, optional = unwrap_optional(split_generic(p['type'])[1][0])
    vt = ValueType(module, value_type, what)
    a = args_of(p['value'])
    extra = [k for k, v in a.items() if k != 'title' and not is_nil(v)]
    if extra:
        raise MetadataError(f'{what}: unsupported @Property arguments {extra}')
    return {'capabilities': 0, 'identifier': name, 'isOptional': optional,
            'title': localized_node(a['title'], what), 'valueType': vt.json}


def entity(module, entry):
    name = entry['typeName']
    shown, numeric = display_type_name(entry)
    props = []
    for p in entry.get('properties', []):
        if p['label'].startswith('_') and split_generic(p['type'])[0] == 'AppIntents.EntityProperty':
            if p.get('valueKind') != 'InitCall':
                raise MetadataError(f'{name}.{p["label"]}: @Property arguments must be compile-time constants')
            props.append(entity_property(module, entry, p))
    out = {
        'assistantDefinedSchemas': [],
        'availabilityAnnotations': availability(entry),
        'defaultQueryIdentifier': entity_query_type(module, entry),
        'displayTypeName': shown,
        'effectiveBundleIdentifiers': [],
        'entitySyncMetadata': {'entitySyncType': 0},
        'fullyQualifiedTypeName': name,
        'mangledTypeName': entry['mangledTypeName'],
        'mangledTypeNameByBundleIdentifier': {},
        'properties': props,
        'requiredCapabilities': [],
        'systemProtocolMetadata': [],
        'systemProtocolMetadataV2': [],
        'transient': False,
        'typeName': short_name(name),
        'typeSpecificMetadata': [],
        'visibilityMetadata': dict(VISIBLE),
    }
    if numeric is not None:
        out['numericFormatTypeName'] = numeric
    return out


QUERY_CAPABILITIES = {'AppIntents.EnumerableEntityQuery': 1, 'AppIntents.EntityStringQuery': 4}
UNSUPPORTED_QUERIES = ('AppIntents.EntityPropertyQuery', 'AppIntents.IndexedEntityQuery', 'AppIntents.IntentValueQuery')


def query(module, entry, default_for):
    name = entry['typeName']
    for proto in UNSUPPORTED_QUERIES:
        if module.conforms(entry, proto):
            raise MetadataError(f'{name}: {proto} is not supported')
    if any(p['label'].startswith('_') and split_generic(p['type'])[0] == 'AppIntents.IntentParameter'
           for p in entry.get('properties', [])):
        raise MetadataError(f'{name}: query parameters are not supported')
    ent = alias(entry, 'Entity')
    if ent is None:
        raise MetadataError(f'{name}: no Entity in const values')
    caps = 66
    for proto, bit in QUERY_CAPABILITIES.items():
        if module.conforms(entry, proto):
            caps |= bit
    entity_name = short_name(ent['substitutedTypeName'])
    return {
        'availabilityAnnotations': availability(entry),
        'capabilities': caps,
        'defaultQueryForEntity': name in default_for,
        'effectiveBundleIdentifiers': [],
        'entityType': entity_name,
        'fullyQualifiedIdentifier': name,
        'identifier': short_name(name),
        'mangledTypeName': entry['mangledTypeName'],
        'mangledTypeNameByBundleIdentifier': {},
        'parameters': [],
        'queryType': short_name(name),
        'resultValueType': {'entity': {'wrapper': {'typeName': entity_name}}},
        'sortingOptions': [],
        'visibilityMetadata': dict(VISIBLE),
    }


def display_representation(node, what):
    kind = node['valueKind']
    if kind in ('RawLiteral', 'InterpolatedStringLiteral'):
        return {'title': localized_node(node, what)}
    if kind != 'InitCall' or node['value']['type'] != 'AppIntents.DisplayRepresentation':
        raise MetadataError(f'{what}: unsupported DisplayRepresentation form {kind}')
    out = {}
    for label, arg in args_of(node['value']).items():
        if is_nil(arg):
            continue
        if label == 'title':
            out['title'] = localized_node(arg, what)
        elif label == 'subtitle':
            out['subtitle'] = localized_node(arg, what)
        elif label == 'image':
            img = arg['value'] if arg['valueKind'] == 'InitCall' else None
            ia = args_of(img) if img else {}
            if not img or set(k for k, v in ia.items() if not is_nil(v)) != {'systemName'}:
                raise MetadataError(f'{what}: only DisplayRepresentation.Image(systemName:) is supported')
            image = {'systemImageName': {'_0': literal(ia['systemName'], what)}}
            out['image'] = image
            out['imageV2'] = image
        else:
            raise MetadataError(f'{what}: unsupported DisplayRepresentation argument {label}')
    return out


def enum(module, entry):
    name = entry['typeName']
    shown, _ = display_type_name(entry)
    reps = prop(entry, 'caseDisplayRepresentations')
    if reps is None or reps.get('valueKind') != 'Dictionary':
        raise MetadataError(f'{name}.caseDisplayRepresentations must be a compile-time constant dictionary')
    by_case = {}
    for item in reps['value']:
        key = item['key']
        if key['valueKind'] != 'Enum':
            raise MetadataError(f'{name}.caseDisplayRepresentations: keys must be enum cases')
        by_case[key['value']['name']] = display_representation(item['value'], f'{name}.{key["value"]["name"]}')
    cases = []
    for c in entry.get('cases', []):
        if c['name'] not in by_case:
            raise MetadataError(f'{name}: case {c["name"]} has no display representation')
        cases.append({'displayRepresentation': by_case[c['name']], 'identifier': c.get('rawValue', c['name'])})
    return {
        'assistantDefinedSchemas': [],
        'availabilityAnnotations': availability(entry),
        'cases': cases,
        'displayTypeName': shown,
        'effectiveBundleIdentifiers': [],
        'fullyQualifiedTypeName': name,
        'identifier': short_name(name),
        'isSystem': False,
        'mangledTypeName': entry['mangledTypeName'],
        'mangledTypeNameByBundleIdentifier': {},
        'systemProtocolMetadata': [],
        'visibilityMetadata': dict(VISIBLE),
    }


# ---------------------------------------------------------------------------
# App Shortcuts

def auto_shortcuts(module, provider):
    what = provider['typeName'] + '.appShortcuts'
    p = prop(provider, 'appShortcuts')
    if p is None or p.get('valueKind') != 'Builder':
        raise MetadataError(f'{what} must be a compile-time constant builder expression')
    out = []
    for member in p['value']['members']:
        if member.get('kind') != 'buildExpression' or member['element']['valueKind'] != 'InitCall':
            raise MetadataError(f'{what}: unsupported builder member {member.get("kind")}')
        a = args_of(member['element']['value'])
        intent = a['intent']
        if intent['valueKind'] != 'InitCall' or intent['value']['arguments']:
            raise MetadataError(f'{what}: AppShortcut intent must be a plain initializer')
        intent_entry = module.entry(intent['type'])
        if intent_entry is None:
            raise MetadataError(f'{what}: intent {intent["type"]} is not in this module')
        shortcut = {
            'actionIdentifier': short_name(intent['type']),
            'availabilityAnnotations': availability(intent_entry),
            'phraseTemplates': [localized(string_template(ph, what)) for ph in a['phrases']['value']],
            'systemImageName': '' if is_nil(a.get('systemImageName')) else literal(a['systemImageName'], what),
        }
        if not is_nil(a.get('shortTitle')):
            shortcut['shortTitle'] = localized_node(a['shortTitle'], what)
        extra = set(k for k, v in a.items() if not is_nil(v)) - {'intent', 'phrases', 'shortTitle', 'systemImageName'}
        if extra:
            raise MetadataError(f'{what}: unsupported AppShortcut arguments {sorted(extra)}')
        out.append(shortcut)
    return out


# ---------------------------------------------------------------------------
# extract.actionsdata

UNSUPPORTED_KINDS = ('AppIntents.TransientAppEntity', 'AppIntents.AppIntentsPackage', 'AppIntents.AppUnionValue',
                     'AppIntents._AssistantIntentsProvider', 'AppIntents.AssistantSchemaIntent',
                     'AppIntents.AssistantSchemaEntity', 'AppIntents.AssistantSchemaEnum', 'AppIntents.IndexedEntity')


def actions_data(module, xcode_version, uttypes):
    for e in module.entries:
        for proto in UNSUPPORTED_KINDS:
            if module.conforms(e, proto):
                raise MetadataError(f'{e["typeName"]}: {proto} is not supported')
    entities = module.of('AppIntents.AppEntity')
    default_for = {entity_query_type(module, e) for e in entities}
    providers = module.of('AppIntents.AppShortcutsProvider')
    if len(providers) > 1:
        raise MetadataError('more than one AppShortcutsProvider in the module')
    data = {
        'actions': {short_name(e['typeName']): action(module, e, uttypes) for e in module.of('AppIntents.AppIntent')},
        'assistantEntities': [],
        'assistantIntentNegativePhrases': [],
        'assistantIntents': [],
        'autoShortcuts': auto_shortcuts(module, providers[0]) if providers else [],
        'entities': {short_name(e['typeName']): entity(module, e) for e in entities},
        'enums': [enum(module, e) for e in module.of('AppIntents.AppEnum')],
        'generator': {'name': 'xcode-tools', 'version': xcode_version},
        'negativePhrases': [],
        'queries': {short_name(e['typeName']): query(module, e, default_for) for e in module.of('AppIntents.EntityQuery')},
        'shortcutTileColor': 14,
        'version': 1,
    }
    if providers:
        data['autoShortcutProviderMangledName'] = providers[0]['mangledTypeName']
        for label in ('shortcutTileColor', 'negativePhrases'):
            if prop(providers[0], label) is not None:
                raise MetadataError(f'{providers[0]["typeName"]}.{label} is not supported')
    return data


def swift_json(value):
    """Swift JSONEncoder(.sortedKeys) bytes: compact, '/' escaped, UTF-8, integral doubles bare."""
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return text.replace('/', '\\/').encode('utf-8')


def version_json(xcode_version):
    return ('{\n  "toolsVersion" : "%s",\n  "version" : "3.0"\n}' % xcode_version).encode('utf-8')


# ---------------------------------------------------------------------------
# App Shortcuts training model (root.ssu.yaml), as appintentsnltrainingprocessor builds it.
# A mapping is a list of (key, value) tuples so key order is explicit.

def resource_ref(resources, kind, locale):
    return f'ssu://Resources/{kind}/{locale}.yaml' if os.path.isfile(
        os.path.join(resources, kind, f'{locale}.yaml')) else None


def ssu_model(data, bundle_id, app_name, locale, resources):
    """None when the target has no App Shortcuts ("No AppShortcuts found - Skipping.")."""
    shortcuts = data['autoShortcuts']
    if not shortcuts:
        return None
    enums = {e['identifier']: e for e in data['enums']}
    prefix = resource_ref(resources, 'prefix', locale) if locale else None
    negatives = resource_ref(resources, 'standardAppShortcutNegatives', locale) if locale else None
    params = []  # (variable name, synonyms) in first-use order

    def variable_for(vt):
        if 'entity' in vt:
            name = vt['entity']['wrapper']['typeName']
            synonyms = [data['entities'][name]['displayTypeName']['key']]
        else:
            name = vt['linkEnumeration']['wrapper']['identifier']
            synonyms = [c['displayRepresentation']['title']['key'] for c in enums[name]['cases']]
        if name not in [p[0] for p in params]:
            params.append((name, synonyms))
        return name

    intents = []
    for i, sc in enumerate(shortcuts):
        act = data['actions'][sc['actionIdentifier']]
        by_name = {p['name']: variable_for(p['valueType']) for p in act['parameters']
                   if 'entity' in p['valueType'] or 'linkEnumeration' in p['valueType']}

        def sub(m):
            key = m.group(1)
            if key == 'applicationName':
                return '${+applicationName}'
            if key not in by_name:
                raise MetadataError(f'{sc["actionIdentifier"]}: phrase parameter {key} is not an entity or enum parameter')
            return '${' + by_name[key] + '}'
        utterances = []
        for ph in sc['phraseTemplates']:
            text = re.sub(r'\$\{([^}]*)\}', sub, ph['key'])
            utterances.append('{${+prefix} }' + text if prefix else text)
        corpus = [[('locale', locale), ('utterances', utterances)]] if locale else []
        intents.append([('metadata', [('name', f'{sc["actionIdentifier"]}_{i}'), ('title', act['title']['key'])]),
                        ('corpuses', [('training', corpus)])])
    negative = []
    if negatives:
        negative = ['{${+prefix} }${+standardAppShortcutNegatives}' if prefix else '${+standardAppShortcutNegatives}']
    intents.append([('metadata', [('name', '+negative')]),
                    ('corpuses', [('training', [[('locale', locale), ('utterances', negative)]] if locale else [])])])
    model = [('apiVersion', 'ssu/v1'),
             ('nlu', [('shortcuts', [('bundleIdentifier', bundle_id), ('intents', intents)])])]
    if locale:
        def var(name, kind, synonyms):
            return [('name', name), ('type', kind), ('definitions', [[('locale', locale), ('synomyms', synonyms)]])]
        variables = [var('+applicationName', 'ssu/expansion', [app_name])]
        # Xcode emits these in Swift hash order, which varies between its runs; first-use order is fixed.
        variables += [var(name, 'ssu/parameter', synonyms) for name, synonyms in params]
        if prefix:
            variables.append(var('+prefix', 'ssu/expansion', [('$ref', prefix)]))
        if negatives:
            variables.append(var('+standardAppShortcutNegatives', 'ssu/expansion', [('$ref', negatives)]))
        model.append(('variables', variables))
    return model


def is_mapping(v):
    return isinstance(v, list) and bool(v) and all(isinstance(x, tuple) for x in v)


def flatten(model, path=''):
    """'path.to.key=value' lines; the Insecure.MD5 of these, newline-joined, names the NLU archive."""
    if is_mapping(model):
        return [line for k, v in model for line in flatten(v, f'{path}{k}.')]
    if isinstance(model, list):
        return [line for i, v in enumerate(model) for line in flatten(v, f'{path}{i}.')]
    return [f'{path[:-1]}={model}']


def model_hash(model):
    return hashlib.md5('\n'.join(flatten(model)).encode('utf-8')).hexdigest()


# Yams (libyaml) output: block style, indent 2, indentless sequences, no line folding.
YAML_RESOLVERS = [re.compile(p) for p in (
    r'^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$',
    r'^(?:[-+]?0b[0-1_]+|[-+]?0o?[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$',
    r'^(?:[-+]?(?:[0-9][0-9_]*)(?:\.[0-9_]*)?(?:[eE][-+]?[0-9]+)?|\.[0-9_]+(?:[eE][-+][0-9]+)?'
    r'|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$',
    r'^(?:<<)$',
    r'^(?:~|null|Null|NULL|)$',
    r'^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]|[0-9][0-9][0-9][0-9]-[0-9][0-9]?-[0-9][0-9]?'
    r'(?:[Tt]|[ \t]+)[0-9][0-9]?:[0-9][0-9]:[0-9][0-9](?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$',
    r'^(?:=)$')]
YAML_ESCAPES = {'\0': '0', '\a': 'a', '\b': 'b', '\t': 't', '\n': 'n', '\v': 'v', '\f': 'f', '\r': 'r',
                '\x1b': 'e', '"': '"', '\\': '\\', '\x85': 'N', '\xa0': '_', '\u2028': 'L', '\u2029': 'P'}


def yaml_printable(ch):
    c = ord(ch)
    return c == 0x0A or 0x20 <= c <= 0x7E or 0xA0 <= c <= 0xD7FF or (0xE000 <= c <= 0xFFFD and c != 0xFEFF)


def yaml_scalar(s):
    """A string as Yams writes it: plain, single-quoted (non-str resolution or indicators), or double-quoted."""
    if any(not yaml_printable(ch) or ch in '\n\x85\u2028\u2029' for ch in s):
        out = ''
        for ch in s:
            c = ord(ch)
            if ch in YAML_ESCAPES:
                out += '\\' + YAML_ESCAPES[ch]
            elif yaml_printable(ch):
                out += ch
            else:
                out += '\\x%02X' % c if c <= 0xFF else '\\u%04X' % c if c <= 0xFFFF else '\\U%08X' % c
        return '"' + out + '"'
    plain = bool(s) and not any(r.match(s) for r in YAML_RESOLVERS) and not (
        s.startswith('---') or s.startswith('...') or s[0] == ' ' or s[-1] == ' ')
    for i, ch in enumerate(s if plain else ''):
        followed_ws = i + 1 == len(s) or s[i + 1] in ' \t'
        if i == 0 and (ch in '#,[]{}&*!|>\'"%@`' or (ch in '?:-' and followed_ws)):
            plain = False
        elif i > 0 and ((ch == ':' and followed_ws) or (ch == '#' and s[i - 1] in ' \t')):
            plain = False
    return s if plain else "'" + s.replace("'", "''") + "'"


def yaml_dump(model):
    lines = []

    def mapping(pairs, indent, first_lead=None):
        for i, (k, v) in enumerate(pairs):
            lead = first_lead if i == 0 and first_lead is not None else ' ' * indent
            node(v, indent, lead + yaml_scalar(k) + ':')

    def node(v, indent, head):
        if is_mapping(v):
            lines.append(head)
            mapping(v, indent + 2)
        elif isinstance(v, list):
            if not v:
                lines.append(head + ' []')
                return
            lines.append(head)
            for item in v:
                if is_mapping(item):
                    mapping(item, indent + 2, ' ' * indent + '- ')
                else:
                    lines.append(' ' * indent + '- ' + yaml_scalar(item))
        else:
            lines.append(head + ' ' + yaml_scalar(v))

    mapping(model, 0)
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# NLU archive: every phrase expanded into a FlatBuffer (reference FlatBufferBuilder layout,
# fields added in declaration order), then LZFSE-compressed.

def load_resource_list(resources, ref):
    path = os.path.join(resources, ref[len('ssu://Resources/'):])
    items = []
    for line in open(path, encoding='utf-8').read().splitlines():
        if line.startswith('- '):
            items.append(line[2:])
        elif line.strip():
            raise MetadataError(f'{path}: unsupported resource line {line!r}')
    return items


def expand(template, variables):
    """'{${+prefix} }Open ${X} in ${+applicationName}' -> strings; the leftmost slot varies slowest."""
    parts, i = [], 0
    while i < len(template):
        if template.startswith('${', i):
            j = template.index('}', i)
            name = template[i + 2:j]
            if name not in variables:
                raise MetadataError(f'undefined SSU variable {name}')
            parts.append([s for syn in variables[name] for s in expand(syn, variables)])
            i = j + 1
        elif template[i] == '{':
            depth, j = 1, i + 1
            while depth:
                if template.startswith('${', j):
                    j = template.index('}', j) + 1
                    continue
                depth += {'{': 1, '}': -1}.get(template[j], 0)
                j += 1
            parts.append([''] + expand(template[i + 1:j - 1], variables))
            i = j
        else:
            j = i
            while j < len(template) and template[j] != '{' and not template.startswith('${', j):
                j += 1
            parts.append([template[i:j]])
            i = j
    out = ['']
    for alternatives in parts:
        out = [a + b for a in out for b in alternatives]
    return out


def get_path(model, *keys):
    for k in keys:
        model = dict(model)[k]
    return model


class FlatBufferBuilder:
    """Back-to-front builder with the reference C++ FlatBufferBuilder's alignment and vtable dedup."""

    def __init__(self):
        self.buf = bytearray()  # reversed: buf[0] is the last byte of the finished buffer
        self.minalign = 1
        self.vtables = []

    def size(self):
        return len(self.buf)

    def pad(self, n):
        self.buf += bytes(n)

    def align(self, n):
        self.minalign = max(self.minalign, n)
        self.pad(-self.size() % n)

    def prealign(self, length, alignment):
        self.minalign = max(self.minalign, alignment)
        self.pad(-(self.size() + length) % alignment)

    def push(self, data):
        self.buf += data[::-1]

    def scalar(self, fmt, value):
        self.align(struct.calcsize(fmt))
        self.push(struct.pack('<' + fmt, value))
        return self.size()

    def refer(self, off):
        self.align(4)
        return self.size() - off + 4

    def string(self, s):
        data = s.encode('utf-8')
        self.prealign(len(data) + 1, 4)
        self.pad(1)
        self.push(data)
        return self.scalar('I', len(data))

    def vector(self, offsets):
        self.prealign(len(offsets) * 4, 4)
        for off in reversed(offsets):
            self.scalar('I', self.refer(off))
        return self.scalar('I', len(offsets))

    def table(self, fields):
        """fields: [(field id, 'offset' or a struct format, value)] in the order they are added."""
        start = self.size()
        locs = [(fid, self.scalar('I', self.refer(v)) if kind == 'offset' else self.scalar(kind, v))
                for fid, kind, v in fields]
        table = self.scalar('i', 0)
        slots = [0] * (max(fid for fid, _ in locs) + 1)
        for fid, loc in locs:
            slots[fid] = table - loc
        vtable = struct.pack(f'<{len(slots) + 2}H', 4 + 2 * len(slots), table - start, *slots)
        use = next((pos for pos in self.vtables if bytes(self.buf[pos - len(vtable):pos][::-1]) == vtable), None)
        if use is None:
            self.push(vtable)
            use = self.size()
            self.vtables.append(use)
        self.buf[table - 4:table] = struct.pack('<i', use - table)[::-1]
        return table

    def finish(self, root):
        self.prealign(4, self.minalign)
        self.scalar('I', self.refer(root))
        return bytes(self.buf[::-1])


def nlu_archive(model, resources, timestamp, version_hash):
    variables, kinds, locale = {}, {}, None
    for v in dict(model)['variables']:
        v = dict(v)
        definition = dict(v['definitions'][0])
        locale = definition['locale']
        synonyms = definition['synomyms']
        variables[v['name']] = load_resource_list(resources, dict(synonyms)['$ref']) if is_mapping(synonyms) else synonyms
        kinds[v['name']] = v['type']
    shortcuts = get_path(model, 'nlu', 'shortcuts')
    b = FlatBufferBuilder()
    data_version = b.string(version_hash)
    user_data = b.vector([])
    encoder_version = b.string('1.0')
    metadata = b.table([(0, 'offset', data_version), (1, 'q', timestamp), (2, 'offset', user_data),
                        (3, 'offset', encoder_version)])
    loc = b.string(locale)

    def examples(utterances):
        out = []
        for u in utterances:
            for text in expand(u, variables):
                s = b.string(' '.join(w for w in text.split(' ') if w))
                out.append(b.table([(0, 'B', 1), (1, 'offset', b.table([(0, 'offset', s)]))]))
        return b.vector(out)

    group_name = b.string(dict(shortcuts)['bundleIdentifier'])
    positives, negative = [], []
    for intent in dict(shortcuts)['intents']:
        name = get_path(intent, 'metadata', 'name')
        training = get_path(intent, 'corpuses', 'training')
        utterances = dict(training[0])['utterances'] if training else []
        if name == '+negative':
            negative = utterances
            continue
        n = b.string(name)
        used = []
        for u in utterances:
            for var in re.findall(r'\$\{([^}]*)\}', u):
                if kinds.get(var) == 'ssu/parameter' and var not in used:
                    used.append(var)
        params = []
        for var in used:
            pn = b.string(var)
            pv = b.string(variables[var][0])
            params.append(b.table([(0, 'offset', pn), (1, 'offset', pv)]))
        pvec = b.vector(params)
        evec = examples(utterances)
        positives.append(b.table([(0, 'offset', n), (1, 'offset', pvec), (2, 'offset', evec)]))
    intents = b.vector(positives)
    negatives = examples(negative)
    group = b.table([(0, 'offset', group_name), (1, 'offset', intents), (2, 'offset', negatives)])
    category = b.table([(1, 'offset', b.vector([group]))])
    root = b.table([(0, 'H', 1), (1, 'offset', metadata), (2, 'offset', loc), (3, 'offset', b.vector([category]))])
    return b.finish(root)


# ---------------------------------------------------------------------------
# LZFSE encoder: a port of the reference lzfse encoder (github.com/lzfse/lzfse, which Apple's
# libcompression matches byte for byte): LZVN below 4096 bytes, LZFSE v2 blocks above.

LZFSE_HASH_BITS = 14
LZFSE_HASH_WIDTH = 4
LZFSE_GOOD_MATCH = 40
LZFSE_LZVN_THRESHOLD = 4096
LZFSE_MAX_L = 315
LZFSE_MAX_M = 2359
LZFSE_MAX_D = 262139
LZFSE_MAX_MATCH = 100 * LZFSE_MAX_M
LZFSE_MATCHES_PER_BLOCK = 10000
LZFSE_LITERALS_PER_BLOCK = 40000
L_EXTRA = [0] * 16 + [2, 3, 5, 8]
L_BASE = list(range(16)) + [16, 20, 28, 60]
M_EXTRA = [0] * 16 + [3, 5, 8, 11]
M_BASE = list(range(16)) + [16, 24, 56, 312]
D_EXTRA = [i // 4 for i in range(64)]
D_BASE = [0, 1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 28, 36, 44, 52, 60, 76, 92, 108, 124, 156, 188, 220,
          252, 316, 380, 444, 508, 636, 764, 892, 1020, 1276, 1532, 1788, 2044, 2556, 3068, 3580, 4092,
          5116, 6140, 7164, 8188, 10236, 12284, 14332, 16380, 20476, 24572, 28668, 32764, 40956, 49148,
          57340, 65532, 81916, 98300, 114684, 131068, 163836, 196604, 229372]


def base_symbol(bases, value):
    lo, hi = 0, len(bases) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if bases[mid] <= value:
            lo = mid
        else:
            hi = mid - 1
    return lo


def clz32(x):
    return 32 - x.bit_length()


def fse_normalize(nstates, counts):
    total = sum(counts)
    step = (1 << 31) // total if total else 0
    shift = clz32(nstates) - 1
    freq, remaining, max_f, max_sym = [], nstates, 0, 0
    for i, t in enumerate(counts):
        f = (((t * step) >> shift) + 1) >> 1
        if f == 0 and t:
            f = 1
        freq.append(f)
        remaining -= f
        if f > max_f:
            max_f, max_sym = f, i
    if -remaining < (max_f >> 2):
        freq[max_sym] += remaining
    else:
        overrun, sh = -remaining, 3
        while overrun:
            for sym in range(len(freq)):
                if freq[sym] > 1:
                    n = min((freq[sym] - 1) >> sh, overrun)
                    freq[sym] -= n
                    overrun -= n
                    if overrun == 0:
                        break
            sh -= 1
    return freq


def fse_encoder_table(nstates, freq):
    table, offset, n_clz = {}, 0, clz32(nstates)
    for i, f in enumerate(freq):
        if f:
            k = clz32(f) - n_clz
            # k == 0 (one symbol owns every state): delta1 is never used; C shifts by -1 there.
            table[i] = ((f << k) - nstates, k, offset - f + (nstates >> k),
                        offset - f + (nstates >> (k - 1)) if k else 0)
            offset += f
    return table


class BitWriter:
    def __init__(self, out):
        self.out, self.accum, self.nbits = out, 0, 0

    def push(self, n, bits):
        self.accum |= bits << self.nbits
        self.nbits += n

    def flush(self):
        n = self.nbits & ~7
        self.out += (self.accum & ((1 << n) - 1)).to_bytes(n // 8, 'little')
        self.accum >>= n
        self.nbits -= n

    def finish(self):
        n = (self.nbits + 7) & ~7
        self.out += self.accum.to_bytes(n // 8, 'little')
        self.accum = 0
        self.nbits -= n


def fse_encode(state, entry, out, symbol):
    s0, k, delta0, delta1 = entry[symbol]
    nbits, delta = (k, delta0) if state >= s0 else (k - 1, delta1)
    out.push(nbits, state & ((1 << nbits) - 1))
    return delta + (state >> nbits)


def freq_code(v):
    fixed = {0: (2, 0), 1: (2, 2), 2: (3, 1), 3: (3, 5), 4: (5, 3), 5: (5, 11), 6: (5, 19), 7: (5, 27)}
    if v in fixed:
        return fixed[v]
    return (8, 7 + ((v - 8) << 4)) if v < 24 else (14, ((v - 24) << 4) + 15)


class LzfseBlockEncoder:
    def __init__(self, src):
        self.src = src
        self.out = bytearray()
        self.l, self.m, self.d, self.lits = [], [], [], bytearray()
        self.src_literal = 0

    def push_lmd(self, L, M, D):
        if len(self.l) + 1 + 8 > LZFSE_MATCHES_PER_BLOCK or len(self.lits) + L + 16 > LZFSE_LITERALS_PER_BLOCK:
            return False
        self.l.append(L)
        self.m.append(M)
        self.d.append(D)
        self.lits += self.src[self.src_literal:self.src_literal + L]
        self.src_literal += L + M
        return True

    def push_match(self, pos, ref, length):
        saved = (len(self.l), len(self.lits), self.src_literal)
        L, M, D = pos - self.src_literal, length, pos - ref
        ok = True
        while ok and L > LZFSE_MAX_L:
            ok = self.push_lmd(LZFSE_MAX_L, 0, 1)
            L -= LZFSE_MAX_L
        while ok and M > LZFSE_MAX_M:
            ok = self.push_lmd(L, LZFSE_MAX_M, D)
            L, M = 0, M - LZFSE_MAX_M
        if ok and (L > 0 or M > 0):
            ok = self.push_lmd(L, M, D)
        if not ok:
            n, nl, self.src_literal = saved
            del self.l[n:], self.m[n:], self.d[n:], self.lits[nl:]
        return ok

    def match(self, pos, ref, length):
        if not self.push_match(pos, ref, length):
            self.encode_block()
            if not self.push_match(pos, ref, length):
                raise MetadataError('lzfse: match does not fit in an empty block')

    def literals(self, L):
        pos = self.src_literal + L
        self.match(pos, pos - 1, 0)

    def encode_block(self):
        if not self.lits and not self.l:
            return
        lits = self.lits + bytes(-len(self.lits) % 4)
        d_values, d_prev = [], 0
        for d in self.d:
            if d == d_prev:
                d_values.append(0)
            else:
                d_values.append(d)
                d_prev = d
        l_occ, m_occ, d_occ, lit_occ = [0] * 20, [0] * 20, [0] * 64, [0] * 256
        for v in self.l:
            l_occ[base_symbol(L_BASE, v)] += 1
        for v in self.m:
            m_occ[base_symbol(M_BASE, v)] += 1
        for v in d_values:
            d_occ[base_symbol(D_BASE, v)] += 1
        for c in lits:
            lit_occ[c] += 1
        l_freq, m_freq = fse_normalize(64, l_occ), fse_normalize(64, m_occ)
        d_freq, lit_freq = fse_normalize(256, d_occ), fse_normalize(1024, lit_occ)
        freq_bytes = bytearray()
        fw = BitWriter(freq_bytes)
        for v in l_freq + m_freq + d_freq + lit_freq:
            fw.push(*freq_code(v))
            fw.flush()
        fw.finish()
        header_size = 32 + len(freq_bytes)

        lit_payload = bytearray()
        w = BitWriter(lit_payload)
        enc = fse_encoder_table(1024, lit_freq)
        st = [0, 0, 0, 0]
        for i in range(len(lits) - 4, -1, -4):
            for j in (3, 2, 1, 0):
                st[j] = fse_encode(st[j], enc, w, lits[i + j])
            w.flush()
        w.finish()
        literal_bits = w.nbits

        lmd_payload = bytearray(8)
        w = BitWriter(lmd_payload)
        encs = (fse_encoder_table(64, l_freq), fse_encoder_table(64, m_freq), fse_encoder_table(256, d_freq))
        ls = ms = ds = 0
        for i in range(len(self.l) - 1, -1, -1):
            sym = base_symbol(D_BASE, d_values[i])
            w.push(D_EXTRA[sym], d_values[i] - D_BASE[sym])
            ds = fse_encode(ds, encs[2], w, sym)
            sym = base_symbol(M_BASE, self.m[i])
            w.push(M_EXTRA[sym], self.m[i] - M_BASE[sym])
            ms = fse_encode(ms, encs[1], w, sym)
            sym = base_symbol(L_BASE, self.l[i])
            w.push(L_EXTRA[sym], self.l[i] - L_BASE[sym])
            ls = fse_encode(ls, encs[0], w, sym)
            w.flush()
        w.finish()
        lmd_bits = w.nbits

        f0 = len(lits) | len(lit_payload) << 20 | len(self.l) << 40 | (7 + literal_bits) << 60
        f1 = st[0] | st[1] << 10 | st[2] << 20 | st[3] << 30 | len(lmd_payload) << 40 | (7 + lmd_bits) << 60
        f2 = header_size | ls << 32 | ms << 42 | ds << 52
        self.out += struct.pack('<IIQQQ', 0x32787662, sum(self.l) + sum(self.m), f0, f1, f2)
        self.out += freq_bytes + lit_payload + lmd_payload
        self.l, self.m, self.d, self.lits = [], [], [], bytearray()


def lzfse_v2(src):
    enc = LzfseBlockEncoder(src)
    invalid = -4 * LZFSE_MAX_D
    hpos = [invalid] * ((1 << LZFSE_HASH_BITS) * LZFSE_HASH_WIDTH)
    hval = [0] * ((1 << LZFSE_HASH_BITS) * LZFSE_HASH_WIDTH)
    pending = None  # (pos, ref, length)
    end = len(src)
    for pos in range(0, end - 8):
        x = int.from_bytes(src[pos:pos + 4], 'little')
        line = (((x * 2654435761) & 0xffffffff) >> (32 - LZFSE_HASH_BITS)) * LZFSE_HASH_WIDTH
        hp, hv = hpos[line:line + 4], hval[line:line + 4]
        if pos >= enc.src_literal:
            inc_len, inc_ref = 0, 0
            for k in range(4):
                ref = hp[k]
                if hv[k] != x or ref + LZFSE_MAX_D < pos:
                    continue
                length, max_len = 4, end - pos - 8
                while length < max_len:
                    a, b = src[ref + length:ref + length + 8], src[pos + length:pos + length + 8]
                    if a == b:
                        length += 8
                        continue
                    length += next(i for i in range(8) if a[i] != b[i])
                    break
                if length > inc_len:
                    inc_len, inc_ref = length, ref
            if inc_len == 0:
                if pos - enc.src_literal > 8 * LZFSE_MAX_L:
                    if pending:
                        enc.match(*pending)
                        pending = None
                    else:
                        enc.literals(LZFSE_MAX_L)
            else:
                inc_len = min(inc_len, LZFSE_MAX_MATCH)
                ipos, iref = pos, inc_ref
                while ipos > enc.src_literal and iref > 0 and src[iref - 1] == src[ipos - 1]:
                    ipos -= 1
                    iref -= 1
                incoming = (ipos, iref, inc_len + pos - ipos)
                if incoming[2] >= LZFSE_GOOD_MATCH:
                    enc.match(*incoming)
                    pending = None
                elif pending is None:
                    pending = incoming
                elif pending[0] + pending[2] <= incoming[0]:
                    enc.match(*pending)
                    pending = incoming
                else:
                    enc.match(*(incoming if incoming[2] > pending[2] else pending))
                    pending = None
        hpos[line:line + 4] = [pos] + hp[:3]
        hval[line:line + 4] = [x] + hv[:3]
    if pending:
        enc.match(*pending)
    if end - enc.src_literal > 0:
        enc.literals(end - enc.src_literal)
    enc.encode_block()
    return bytes(enc.out) + struct.pack('<I', 0x24787662)


def lzvn(src):
    """LZVN payload (with its 8-byte end-of-stream), or None if the reference encoder would fail."""
    n = len(src)
    buf = src + bytes(16)  # the C code reads up to 8 bytes past a literal or match
    out = bytearray()
    state = {'lit': 0, 'd_prev': 0}

    def emit_literal(L):
        p = state['lit']
        while L > 15:
            x = min(L, 271)
            out.extend(struct.pack('<H', 0xE0 + ((x - 16) << 8)))
            out.extend(buf[p:p + x])
            p += x
            L -= x
        if L > 0:
            out.append(0xE0 + L)
            out.extend(buf[p:p + L])
            p += L
        state['lit'] = p

    def emit_match(m_begin, m_end, M, D):
        p, L = state['lit'], m_begin - state['lit']
        while L > 15:
            x = min(L, 271)
            out.extend(struct.pack('<H', 0xE0 + ((x - 16) << 8)))
            out.extend(buf[p:p + x])
            p += x
            L -= x
        if L > 3:
            out.append(0xE0 + L)
            out.extend(buf[p:p + L])
            p += L
            L = 0
        x = min(M, 10 - 2 * L)
        M -= x
        x -= 3
        literal = buf[p:p + L]
        if D == state['d_prev']:
            out.append(0xF0 + (x + 3) if L == 0 else (L << 6) + (x << 3) + 6)
        elif D < 2048 - 2 * 256:
            out.extend(bytes([(D >> 8) + (L << 6) + (x << 3), D & 0xFF]))
        elif D >= (1 << 14) or M == 0 or (x + 3) + M > 34:
            out.append((L << 6) + (x << 3) + 7)
            out.extend(struct.pack('<H', D))
        else:
            x += M
            M = 0
            out.append(0xA0 + (x >> 2) + (L << 3))
            out.extend(struct.pack('<H', (D << 2 | (x & 3)) & 0xFFFF))
        out.extend(literal)
        while M > 15:
            x = min(M, 271)
            out.extend(struct.pack('<H', 0xF0 + ((x - 16) << 8)))
            M -= x
        if M > 0:
            out.append(0xF0 + M)
        state['d_prev'] = D
        state['lit'] = m_end

    def load4(i):
        return int.from_bytes(buf[i:i + 4], 'little') if i >= 0 else 0

    def tzb(v):
        return 4 if v == 0 else ((v & -v).bit_length() - 1) >> 3

    def find(m0, mb, nk):
        if nk < 3:
            return None
        D = mb - m0
        if D <= 0 or D > 0xffff:
            return None
        m_end, cnt = mb + nk, nk
        while cnt == 4 and m_end + 4 < n:
            cnt = tzb(load4(m_end) ^ load4(m_end - D))
            m_end += cnt
        while m0 > 0 and mb > state['lit'] and buf[mb - 1] == buf[m0 - 1]:
            m0 -= 1
            mb -= 1
        M = m_end - mb
        return (mb, m_end, M, D, M - (2 if D < 0x600 else 3))  # m_begin, m_end, M, D, K

    if n >= 8:
        nvals = 1 << 14
        idx = [[0, 0, 0, 0] for _ in range(nvals)]
        val = [[load4(0)] * 4 for _ in range(nvals)]
        pending = None
        for cur in range(0, n - 8):
            vi = load4(cur)
            h = (((vi & 0xffffff) * (1 + (1 << 6) + (1 << 12))) >> 12) & (nvals - 1)
            ei, ev = idx[h], val[h]
            if cur >= state['lit']:
                best = None
                for k in range(4):
                    m1 = find(ei[k], cur, tzb(ev[k] ^ vi))
                    if m1 and (best is None or m1[4] > best[4] or (m1[4] == best[4] and m1[1] > best[1] + 1)):
                        best = m1
                if state['d_prev']:
                    m1 = find(cur - state['d_prev'], cur, tzb(load4(cur) ^ load4(cur - state['d_prev'])))
                    if m1:
                        m1 = m1[:4] + (m1[2] - 1,)
                        if best is None or m1[4] > best[4] or (m1[4] == best[4] and m1[1] > best[1] + 1):
                            best = m1
                if best is None:
                    if cur - state['lit'] >= 400:
                        if pending:
                            emit_match(*pending[:4])
                            pending = None
                        else:
                            emit_literal(271)
                elif pending is None:
                    pending = best
                elif pending[1] <= best[0]:
                    emit_match(*pending[:4])
                    pending = best
                else:
                    if best[4] > pending[4]:
                        pending = best
                    emit_match(*pending[:4])
                    pending = None
            idx[h] = [cur] + ei[:3]
            val[h] = [vi] + ev[:3]
    emit_literal(n - state['lit'])
    out.extend(struct.pack('<Q', 0x06))
    return bytes(out)


def lzfse_compress(src):
    n = len(src)
    if n >= 8 and n < LZFSE_LZVN_THRESHOLD:
        payload = lzvn(src)
        if len(payload) < n:
            return struct.pack('<III', 0x6e787662, n, len(payload)) + payload + struct.pack('<I', 0x24787662)
    elif n >= LZFSE_LZVN_THRESHOLD:
        return lzfse_v2(src)
    return struct.pack('<II', 0x2d787662, n) + src + struct.pack('<I', 0x24787662)

# ---------------------------------------------------------------------------
# Inputs

def read_list_file(path):
    """Xcode file lists: one path per line; the processor drops backslashes."""
    with open(path, encoding='utf-8') as f:
        return [line.rstrip('\n').replace('\\', '') for line in f if line.strip()]


def load_const_values(paths):
    entries = []
    seen = set()
    for path in paths:
        with open(path, encoding='utf-8') as f:
            for e in json.load(f):
                if e['typeName'] in seen:
                    raise MetadataError(f'{e["typeName"]} appears in more than one const values file')
                seen.add(e['typeName'])
                entries.append(e)
    return entries


def links_app_intents(binary):
    """True if the Mach-O (thin or fat) loads AppIntents.framework."""
    data = open(binary, 'rb').read()
    magic = struct.unpack_from('>I', data, 0)[0]
    slices = []
    if magic in (0xcafebabe, 0xcafebabf):
        n = struct.unpack_from('>I', data, 4)[0]
        wide = magic == 0xcafebabf
        for i in range(n):
            off = 8 + i * (32 if wide else 20)
            slices.append(struct.unpack_from('>Q' if wide else '>I', data, off + 8)[0])
    else:
        slices.append(0)
    for base in slices:
        m = struct.unpack_from('<I', data, base)[0]
        if m not in (0xfeedfacf, 0xfeedface):
            raise MetadataError(f'{binary}: not a Mach-O file')
        ncmds = struct.unpack_from('<I', data, base + 16)[0]
        off = base + (32 if m == 0xfeedfacf else 28)
        for _ in range(ncmds):
            cmd, size = struct.unpack_from('<II', data, off)
            if cmd & 0x7fffffff in (0xc, 0x18, 0x1f, 0x23):  # LOAD/WEAK/REEXPORT/UPWARD dylib
                name_off = struct.unpack_from('<I', data, off + 8)[0]
                name = data[off + name_off:off + size].split(b'\0', 1)[0]
                if b'/AppIntents.framework/' in name:
                    return True
            off += size
    return False


def write_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--module-name', '-m', required=True)
    ap.add_argument('--bundle-identifier', required=True)
    ap.add_argument('--output', '-o', required=True, help='the .app or .appex directory')
    ap.add_argument('--swift-const-vals-list', '-scl', action='append', default=[])
    ap.add_argument('--const-values', nargs='*', default=[])
    ap.add_argument('--binary-file', help='linked executable; extraction is skipped unless it loads AppIntents')
    ap.add_argument('--sdk-root', help='iPhoneOS SDK (UTType identifiers)')
    ap.add_argument('--xcode-version', default='27A266a')
    ap.add_argument('--info-plist', help='Info.plist for App Shortcuts training (default: OUTPUT/Info.plist)')
    ap.add_argument('--ssu-resources', help="Xcode's SiriSSUKitModel.framework Resources directory")
    ap.add_argument('--timestamp', type=int, help='NLU archive timestamp (default: SOURCE_DATE_EPOCH or now)')
    ap.add_argument('--platform-family', default='iOS')
    args = ap.parse_args(argv)

    if args.binary_file and not links_app_intents(args.binary_file):
        print('warning: Metadata extraction skipped, no AppIntents.framework dependency found', file=sys.stderr)
        return 0
    paths = list(args.const_values)
    for lst in args.swift_const_vals_list:
        paths += read_list_file(lst)
    if not paths:
        raise MetadataError(f'no .swiftconstvalues for module {args.module_name} '
                            '(build with -emit-const-values -const-gather-protocols-list)')
    module = Module(load_const_values(paths), args.module_name)
    data = actions_data(module, args.xcode_version, load_uttypes(args.sdk_root))
    if not any(data[k] for k in ('actions', 'entities', 'queries', 'enums', 'autoShortcuts')):
        print('Extracted no relevant App Intents symbols, skipping writing output', file=sys.stderr)
        return 0
    root = os.path.join(args.output, 'Metadata.appintents')
    write_file(os.path.join(root, 'extract.actionsdata'), swift_json(data))
    write_file(os.path.join(root, 'version.json'), version_json(args.xcode_version))
    print(f'{root}: {len(data["actions"])} intents, {len(data["entities"])} entities, '
          f'{len(data["queries"])} queries, {len(data["enums"])} enums, {len(data["autoShortcuts"])} App Shortcuts')
    if args.platform_family != 'iOS':
        return 0  # Xcode trains App Shortcuts for iOS targets only
    write_training(data, args, root)
    return 0


def write_training(data, args, root):
    """appintentsnltrainingprocessor --archive-ssu-assets: root.ssu.yaml and nlu/."""
    if not data['autoShortcuts']:
        return
    info_path = args.info_plist or os.path.join(args.output, 'Info.plist')
    with open(info_path, 'rb') as f:
        info = plistlib.load(f)
    app_name = info.get('CFBundleDisplayName') or info.get('CFBundleName')
    if not app_name:
        raise MetadataError(f'{info_path}: no CFBundleDisplayName or CFBundleName (Unable to parse Info.plist)')
    if not args.ssu_resources:
        raise MetadataError('App Shortcuts need --ssu-resources (Xcode.app/Contents/Frameworks/'
                            'SiriSSUKitModel.framework/Versions/A/Resources)')
    locale = info.get('CFBundleDevelopmentRegion')
    model = ssu_model(data, args.bundle_identifier, app_name, locale, args.ssu_resources)
    write_file(os.path.join(root, 'root.ssu.yaml'), yaml_dump(model).encode('utf-8'))
    if locale is None:
        return  # nothing to train: Xcode writes no nlu/ either
    version_hash = model_hash(model)
    timestamp = args.timestamp
    if timestamp is None:
        timestamp = int(os.environ.get('SOURCE_DATE_EPOCH') or time.time())
    write_file(os.path.join(root, 'nlu', version_hash + '.version'), b'\0')
    write_file(os.path.join(root, 'nlu', 'nlu.lzfse'),
               lzfse_compress(nlu_archive(model, args.ssu_resources, timestamp, version_hash)))
    print(f'{root}: App Shortcuts trained for {locale}, nlu/{version_hash}.version')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except MetadataError as e:
        print(f'error: {e}', file=sys.stderr)
        sys.exit(1)
