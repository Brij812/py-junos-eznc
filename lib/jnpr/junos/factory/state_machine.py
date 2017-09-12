from transitions import Machine
import pyparsing as pp
from collections import OrderedDict
import re
import copy

class Identifiers:
    printables = pp.OneOrMore(pp.printables)
    numbers = pp.Word(pp.nums)
    word = pp.Word(pp.alphanums) | pp.Word(pp.alphas)
    words = pp.OneOrMore(word)
    percentage = pp.Word(pp.nums) + pp.Literal('%')
    header_bar = pp.OneOrMore(pp.Word('-')) + pp.StringEnd()


def data_type(item):
    # should use identifiers class attribute
    try:
        Identifiers.numbers.parseString(item, parseAll=True)
        return int
    except pp.ParseException as ex:
        pass
    return str


class StateMachine(Machine):

    def __init__(self, table_view):
        self._table = table_view
        self._view = self._table.VIEW
        # self._identifiers = [Identifiers.__dict__[key] for key, val in
                             # Identifiers.__dict__.items() if callable(val)]
        # self._identifiers = [pp.OneOrMore(word)]
        self._lines = []
        self.states = ['row_column', 'title_data']
        self.transitions = [
            {'trigger': 'column_provided', 'source': 'start', 'dest': 'row_column',
             'conditions': 'match_columns', 'before': 'check_header_bar',
             'after': 'parse_raw_column'},
            {'trigger': 'check_next_row', 'source': 'row_column', 'dest': 'row_column',
             'conditions': 'prev_next_row_same_type',
             'after': 'parse_raw_column'},
            {'trigger': 'title_provided', 'source': 'start', 'dest': 'title_data',
             'conditions': 'match_title',
             'after': 'parse_title_data'}
        ]
        Machine.__init__(self, states=self.states, transitions=self.transitions,
                         initial='start', send_event=True)

    def parse(self, raw_data):
        self._data = {}
        self._lines = raw_data.splitlines()
        if len(self._view.COLUMN) > 0:
            self.column_provided()
        if self._view.TITLE is not None:
            self.title_provided()
        return self._data

    def match_columns(self, event):
        columns = self._view.COLUMN.values()
        col_parser = reduce(lambda x, y: x & y, [pp.Literal(i) for i in columns])
        for line in self._lines:
            if self._parse_literal(line, col_parser):
                d = set(map(lambda x, y: x in y, columns, [line] * len(columns)))
                if d.pop():
                    current_index = self._lines.index(line)
                    self._lines = self._lines[current_index:]
                    return True
        return False

    def match_title(self, event):
        title = self._view.TITLE
        for line in self._lines:
            if title in line:
                current_index = self._lines.index(line)
                self._lines = self._lines[current_index:]
                return True
        return False

    def _parse_literal(self, line, col_parser):
        try:
            if col_parser.searchString(line):
                return True
        except pp.ParseException as ex:
            return False

    def check_header_bar(self, event):
        line = self._lines[1]
        try:
            Identifiers.header_bar.parseString(line, parseAll=True)
            self._lines.pop(1)
        except pp.ParseException as ex:
            return False
        return True

    def parse_raw_column(self, event):
        col_offsets = {}
        col_order = event.kwargs.get('col_order', OrderedDict())
        line = self._lines[0]
        if len(col_order) == 0:
            for key, column in self._view.COLUMN.items():
                for result, start, end in pp.Literal(column).scanString(line):
                    col_offsets[(start, end)] = result[0]
            user_defined_columns = copy.deepcopy(self._view.COLUMN)
            for key in sorted(col_offsets.iterkeys()):
                for x, y in self._view.COLUMN.items():
                    if col_offsets[key] == user_defined_columns.get(x):
                        col_order[key] = x
                        user_defined_columns.pop(x)
                        break
        # print col_order
        key = self._get_key(event.kwargs.get('key', self._table.KEY))
        items = re.split('\s\s+', self._lines[1].strip())

        post_integer_data_types = event.kwargs.get('check', map(data_type, items))
        index = event.kwargs.get('index', 1)
        col_len = len(col_order)
        for index, line in enumerate(self._lines[index:], start=index):
            items = re.split('\s\s+', line.strip())
            if len(items) == col_len:
                post_integer_data_types, pre_integer_data_types = \
                    map(data_type, items), post_integer_data_types
                if post_integer_data_types == pre_integer_data_types:
                    items = map(lambda x, y: int(x) if y is int else x,
                                items, post_integer_data_types)
                    tmp_dict = dict(zip(col_order.values(), items))
                    if isinstance(key, tuple):
                        self._data[tuple(tmp_dict[i] for i in key)] = tmp_dict
                    else:
                        self._data[tmp_dict[key]] = tmp_dict
                else:
                    break
            elif line.strip() == '':
                self.check_next_row(check=post_integer_data_types, data=self._data,
                                    index=index, col_order=col_order,
                                    key=key)
        return self._data

    def _get_key(self, key):
        if isinstance(key, list):
            if set([i in self._view.COLUMN or i in self._view.COLUMN.values() for i in key]):
                key_temp = []
                for i in key:
                    if i not in self._view.COLUMN and i in self._view.COLUMN.values():
                        for user_provided, from_table in self._view.COLUMN.items():
                            if i == from_table:
                                key_temp.append(user_provided)
                            else:
                                key_temp.append(from_table)
                    else:
                        key_temp.append(i)
                key = tuple(key_temp)
        elif key not in self._view.COLUMN and key in self._view.COLUMN.values():
            for user_provided, from_table in self._view.COLUMN.items():
                if key == from_table:
                    key = user_provided
        return key

    def prev_next_row_same_type(self, event):
        index = event.kwargs.get('index')
        post_integer_data_types = event.kwargs.get('check')
        line = self._lines[index]
        items = re.split('\s\s+', line.strip())
        post_integer_data_types, pre_integer_data_types = \
            map(data_type, items), post_integer_data_types
        return post_integer_data_types == pre_integer_data_types

    def parse_title_data(self, event):
        pre_space_delimit = ''
        obj = re.search('(\s+).*', self._lines[1])
        if obj:
            pre_space_delimit = obj.group(1)
        for line in self._lines[1:]:
            if re.match(pre_space_delimit + '\s+', line):
                break
            if line.startswith(pre_space_delimit):
                try:
                    items = (re.split('\s\s+', line.strip()))
                    item_types = map(data_type, items)
                    key, value = map(lambda x, y: int(x) if y is int else x.strip(),
                                items, item_types)
                    self._data[key] = value
                except ValueError:
                    regex = '(\d+)\s(.*)' if item_types[0]==int else '(.*)\s(\d+)'
                    obj = re.search(regex, line)
                    if obj:
                        items = obj.groups()
                        item_types = map(data_type, items)
                        key, value = map(lambda x, y: int(x) if y is int else x.strip(),
                                         items, item_types)
                        self._data[key] = value
            elif line.strip() == '':
                break
        return self._data
