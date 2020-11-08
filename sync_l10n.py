# Python 3.8+ with type annotations and dataclasses
from __future__ import annotations
import os, shutil, codecs, enum, re
from dataclasses import dataclass
from typing import List, Dict, Optional

SCRIPT_DIR         = os.path.dirname(os.path.realpath(__file__))
CLIENT_DIR         = os.path.join(SCRIPT_DIR, 'client')
L10N_REFERENCE_DIR = os.path.join(SCRIPT_DIR, 'l10n_reference')
L10N_PATCH_DIR     = os.path.join(SCRIPT_DIR, 'l10n_patch')
OUTPUT_DIR         = os.path.join(SCRIPT_DIR, 'output')

@dataclass
class XMLElement:
    name: str
    text: str
    children: List[XMLElement] 

    def find(self, name: str) -> Optional[XMLElement]:
        for child in self.children:
            if child.name == name:
                return child
        return None

def parseAionXml(data: str) -> XMLElement:
    class ParserState(enum.Enum):
        DOCUMENT_START = 1
        XML_DECL_OPENING = 2
        XML_DECL = 3
        XML_DECL_CLOSING = 4
        BEFORE_ROOT = 5
        UNKNOWN_TAG = 6
        BEGIN_TAG = 7
        BEGIN_TAG_ATTRIBUTES = 8
        END_TAG = 9
        TEXT = 10

    state: ParserState = ParserState.DOCUMENT_START
    element_stack: List[XMLElement] = list()
    current_element: Optional[XMLElement] = None
    tag_name_list: List[str] = list()
    text_list_stack: List[List[str]] = list()
    text_list: List[str] = list()

    for c in data:
        if state == ParserState.DOCUMENT_START:
            if c != "<":
                raise Exception("Expected XML declaration opening '<'")
            state = ParserState.XML_DECL_OPENING

        elif state == ParserState.XML_DECL_OPENING:
            if c != "?":
                raise Exception("Expected XML declaration opening '?'")
            state = ParserState.XML_DECL

        elif state == ParserState.XML_DECL:
            if c == "?":
                state = ParserState.XML_DECL_CLOSING

        elif state == ParserState.XML_DECL_CLOSING:
            if c == ">":
                state = ParserState.BEFORE_ROOT
            else:
                state = ParserState.XML_DECL

        elif state == ParserState.BEFORE_ROOT:
            if c == "<":
                state = ParserState.UNKNOWN_TAG

        elif state == ParserState.UNKNOWN_TAG:
            if c == "/":
                state = ParserState.END_TAG
            else:
                tag_name_list.append(c)
                state = ParserState.BEGIN_TAG
        
        elif state == ParserState.BEGIN_TAG:
            if c == ">":
                text_list_stack.append(text_list)
                text_list = list()

                if current_element is not None:
                    element_stack.append(current_element)
                current_element = XMLElement(''.join(tag_name_list), "", list())

                tag_name_list = list()

                state = ParserState.TEXT
            elif c == " ":
                state = ParserState.BEGIN_TAG_ATTRIBUTES
            else:
                tag_name_list.append(c)

        elif state == ParserState.BEGIN_TAG_ATTRIBUTES:
            if c == ">":
                text_list_stack.append(text_list)
                text_list = list()

                if current_element is not None:
                    element_stack.append(current_element)
                current_element = XMLElement(''.join(tag_name_list), "", list())

                tag_name_list = list()

                state = ParserState.TEXT

        elif state == ParserState.END_TAG:
            if c == ">":
                tag_name = ''.join(tag_name_list)
                if tag_name != current_element.name:
                    raise Exception(f"Mismatching tag name: '{tag_name}'")
                tag_name_list = list()

                current_element.text = ''.join(text_list)
                text_list = text_list_stack.pop()

                if len(element_stack) == 0:
                    return current_element
                else:
                    parent_element = element_stack.pop()
                    parent_element.children.append(current_element)
                    current_element = parent_element

                state = ParserState.TEXT
            else:
                tag_name_list.append(c)

        elif state == ParserState.TEXT:
            if c == "<":
                state = ParserState.UNKNOWN_TAG
            else:
                text_list.append(c)

    return None
            
EXPRESSION_RE = re.compile(r"\[%[^%\]].*?\]|%[0-9]")

@dataclass
class AionString:
    tag_name: str
    id_value: int
    name: str
    body: Optional[str]
    message_type: Optional[str]
    display_type: Optional[int]
    ment: Optional[str]
    rank: Optional[int]

    def match_and_repair(self, other: AionString) -> bool:
        if self.id_value != other.id_value:
            print(f"[critical] <id> mismatch: client: {self.id_value}, L10N: {other.id_value}")
            return False

        if self.name != other.name:
            print(f"[error] {self.id_value}: <name> mismatch: client: {self.name}, L10N: {other.name}")
            return False

        # Repair mismatching values
        if self.message_type != other.message_type:
            print(f"[action] {self.id_value}|{self.name}: repairing <message_type>: {self.message_type}, L10N: {other.message_type}")
            other.message_type = self.message_type

        if self.display_type != other.display_type:
            print(f"[action] {self.id_value}|{self.name}: repairing <display_type>: client: {self.display_type}, L10N: {other.display_type}")
            other.display_type = self.display_type

        if self.ment != other.ment:
            print(f"[action] {self.id_value}|{self.name}: repairing <ment>: client: {self.ment}, L10N: {other.ment}")
            other.ment = self.ment

        if self.rank != other.rank:
            print(f"[action] {self.id_value}|{self.name}: repairing <rank>: client: {self.rank}, L10N: {other.rank}")
            other.rank = self.rank

        # match expressions
        if self.body is None and other.body is not None and other.body != '':
            print(f"[warn] {self.id_value}|{self.name}: repairing <body>: client <body> does not exist, but L10N <body> exists: '{other.body}' !")
            other.body = None
        elif self.body is not None and self.body != '' and other.body is None:
            print(f"[error] {self.id_value}|{self.name}: <body> mismatch: client <body> exists: '{self.body}', but L10N <body> does not exist!")
        elif self.body is not None and other.body is not None:
            client_exprs = set(EXPRESSION_RE.findall(self.body))
            l10n_exprs = set(EXPRESSION_RE.findall(other.body))
            if client_exprs != l10n_exprs:
                print(f"[warn] {self.id_value}|{self.name}: <body> expression mismatch: client: {client_exprs}, L10N: {l10n_exprs}")

        return True

VALID_TAGS = set(["id", "name", "body", "message_type", "display_type", "ment", "rank"])

@dataclass
class AionStringDict:
    strings: Dict[int, AionString]

    @staticmethod
    def read(path: str, allow_missing=False) -> AionStringDict:
        strings: Dict[int, AionString] = dict()

        if not os.path.exists(path):
            if allow_missing:
                return AionStringDict(strings)
            else:
                raise Exception(f"'{path}' does not exist!")

        with open(path, 'r', encoding='utf-16') as f:
            xml_string = f.read()
        
        elements = parseAionXml(xml_string)

        for string_element in elements.children:
            if string_element.name != "string" and string_element.name != "string_tip":
                raise Exception(f"Expected <string> or <string_tip> element, got <{string_element.name}> instead!")

            for child in string_element.children:
                if child.name not in VALID_TAGS:
                    raise Exception(f"Unknow tag: <{child.name}>")

            id_element = string_element.find('id')
            if id_element is None:
                raise Exception(f"<id> element not found!")
            id_value = int(id_element.text)

            name_element = string_element.find('name')
            if name_element is None:
                raise Exception(f"<name> element not found for id {id_value}!")
            name_value = name_element.text

            body_element = string_element.find('body')
            body_value = body_element.text if body_element is not None else None

            message_type_element = string_element.find('message_type')
            message_type_value = message_type_element.text if message_type_element is not None else None

            display_type_element = string_element.find('display_type')
            display_type_value = int(display_type_element.text) if display_type_element is not None else None 

            ment_element = string_element.find('ment')
            ment_value = ment_element.text if ment_element is not None else None

            rank_element = string_element.find('rank')
            rank_value = int(rank_element.text) if rank_element is not None else None 
            
            strings[id_value] = AionString(string_element.name, id_value, name_value, body_value, message_type_value, display_type_value, ment_value, rank_value)

        return AionStringDict(strings)

    def write(self, path: str, tag):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-16-le', newline='') as f:
            f.write("\ufeff<?xml version=\"1.0\" encoding=\"utf-16\"?>\r\n")
            f.write(f"<{tag}>\r\n")
            for id_value in sorted(self.strings):
                s: AionString = self.strings[id_value]
                f.write(f"  <{s.tag_name}>\r\n")
                f.write(f"    <id>{s.id_value}</id>\r\n")
                f.write(f"    <name>{s.name}</name>\r\n")
                if s.body is not None:
                    f.write(f"    <body>{s.body}</body>\r\n")
                if s.message_type is not None:
                    f.write(f"    <message_type>{s.message_type}</message_type>\r\n")
                if s.display_type is not None:
                    f.write(f"    <display_type>{s.display_type}</display_type>\r\n")
                if s.ment is not None:
                    f.write(f"    <ment>{s.ment}</ment>\r\n")
                if s.rank is not None:
                    f.write(f"    <rank>{s.rank}</rank>\r\n")
                f.write(f"  </{s.tag_name}>\r\n")
            f.write(f"</{tag}>\r\n")

def case_insensitive_path(base_path: str, rel_path: str):
    rel_path_components = rel_path.split(os.sep)
    for path_component in rel_path_components:
        try:
            matching_names = [name for name in os.listdir(base_path) if path_component.lower() == name.lower()]
            if len(matching_names) > 0:
                base_path = os.path.join(base_path, matching_names[0])
            else:
                base_path = os.path.join(base_path, path_component)
        except:
            base_path = os.path.join(base_path, path_component)
    return base_path

def sync_strings(relpath: str, tag="strings"):
    print()
    print()
    print(f"Checking file '{relpath}'")

    client_dict = AionStringDict.read(case_insensitive_path(CLIENT_DIR, relpath))
    l10n_reference__dict = AionStringDict.read(case_insensitive_path(L10N_REFERENCE_DIR, relpath))
    l10n_patch_dict = AionStringDict.read(case_insensitive_path(L10N_PATCH_DIR, relpath), allow_missing=True)

    # Merge english and custom patch dict
    l10n_dict = AionStringDict({**l10n_reference__dict.strings, **l10n_patch_dict.strings})

    client_dict_keys = set(client_dict.strings.keys())
    l10n_dict_keys = set(l10n_dict.strings.keys())

    # l10n strings not in client
    for k in l10n_dict_keys.difference(client_dict_keys):
        print(f"[warn] {k}|{l10n_dict.strings[k].name} exists in l10n but not in client")
        # Clear key from dictionaries before outputting files
        l10n_dict.strings.pop(k, None)
        l10n_patch_dict.strings.pop(k, None)

    # client strings not handled by l10n
    for k in client_dict_keys.difference(l10n_dict_keys):
        print(f"{k}|{client_dict.strings[k].name} MISSING from l10n!")
        l10n_patch_dict.strings[k] = client_dict.strings[k]

    # check mismatch between kor/eng
    for k in client_dict_keys.intersection(l10n_dict_keys):
        if not client_dict.strings[k].match_and_repair(l10n_dict.strings[k]):
            l10n_patch_dict.strings[k] = client_dict.strings[k]

    # update patch dictionary file
    if len(l10n_patch_dict.strings) > 0:
        l10n_patch_dict.write(os.path.join(L10N_PATCH_DIR, relpath), tag)

    # output translation file
    output_dict = AionStringDict({**l10n_dict.strings, **l10n_patch_dict.strings})
    output_dict.write(os.path.join(OUTPUT_DIR, relpath), tag)
    
def main():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)

    sync_strings(os.path.join('data', 'strings', 'client_strings_bm.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_bmrestrict.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_dic_etc.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_dic_item.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_dic_monster.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_dic_people.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_dic_place.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_etc.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_funcpet.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_gossip.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_item.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_item2.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_level.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_monster.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_msg.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_npc.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_quest.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_skill.xml'))
    sync_strings(os.path.join('data', 'strings', 'client_strings_ui.xml'))
    sync_strings(os.path.join('data', 'strings', 'StringTable_Dialog.xml'))
    sync_strings(os.path.join('data', 'strings', 'stringtable_tip.xml'), tag="string_tips")

    print(f"Copying reference l10n textures to output directory...")
    shutil.copytree(os.path.join(L10N_REFERENCE_DIR, 'textures'), os.path.join(OUTPUT_DIR, 'textures'))
    print(f"Copying reference l10n data\\ui to output directory...")
    shutil.copytree(os.path.join(L10N_REFERENCE_DIR, 'data', 'ui'), os.path.join(OUTPUT_DIR, 'data', 'ui'))
    print(f"Copying reference l10n data\\dialogs to output directory...")
    shutil.copytree(os.path.join(L10N_REFERENCE_DIR, 'data', 'dialogs'), os.path.join(OUTPUT_DIR, 'data', 'dialogs'))
    print(f"Copying reference l10n data\\cutscene to output directory...")
    shutil.copytree(os.path.join(L10N_REFERENCE_DIR, 'data', 'cutscene'), os.path.join(OUTPUT_DIR, 'data', 'cutscene'))
    print(f"Copying reference l10n data\\strings\\error to output directory...")
    shutil.copytree(os.path.join(L10N_REFERENCE_DIR, 'data', 'strings', 'error'), os.path.join(OUTPUT_DIR, 'data', 'strings', 'error'))

    print(f"Applying patch l10n data\\ui\\createinfos.xml...")
    shutil.copyfile(os.path.join(L10N_PATCH_DIR, 'data', 'ui', 'createinfos.xml'), os.path.join(OUTPUT_DIR, 'data', 'ui', 'createinfos.xml'))
    print(f"Applying patch l10n data\\ui\\serverlist.xml...")
    shutil.copyfile(os.path.join(L10N_PATCH_DIR, 'data', 'ui', 'serverlist.xml'), os.path.join(OUTPUT_DIR, 'data', 'ui', 'serverlist.xml'))

if __name__ == '__main__':
    main()
    pass