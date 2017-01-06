# coding:utf-8
import xlrd

# 定义符号
type_array = 'array'
type_dict = 'dict'
type_int = 'int'
type_number = 'number'
type_bool = 'bool'
type_string = 'string'
type_function = 'function'
type_table = 'table'

# 定义简单类型
simple_type_def = {
    type_int: True,
    type_number: True,
    type_bool: True,
    type_string: True,
    type_table: True,
}

# 定义复合类型
complex_token_def = {
    type_array: ('array<', '>'),
    type_dict: ('dict<', '>'),
}


# 判断是否简单类型
def is_simple_type(ty):
    return ty in simple_type_def


# 将整数转换为excel的列
def to_xls_col(num):
    a = ord('A')
    result = ''
    tmp = num
    while True:
        factor = tmp / 26
        remain = tmp % 26
        tmp = factor
        result = chr(remain + a) + result
        if factor == 0:
            break
    return result


# 输出解析错误信息并退出程序
def parse_error(msg):
    print '[parser error]%s' % msg
    exit(1)


# 输出求值错误信息并退出程序
def eval_error(msg):
    print '[eval error]%s' % msg
    exit(2)


# 为字符串内容添加双引号
def add_quout(text):
    return '"' + text + '"'


# 表头符号，每个符号由类型和名字组成，用于构造表格数据结构
class Token:
    def __init__(self, option, decl_type, name, col):
        self.option = option
        self.decl_type = decl_type
        self.name = name
        self.col = col

    def __str__(self):
        if self.decl_type == '':
            return self.name
        else:
            return '%s:%s' % (self.name, self.decl_type)


# 节点解析器，由表头定义构造，根据行数据求值
class NodeParser:
    def __init__(self, node_type, token):
        self.type = node_type
        self.members = []
        self.begin_col = -1
        self.end_col = -1
        self.required = None           # 该节点必须有值，对于容器类型则表示全部子项为空时仍会输出容器节点本身
        self.token = token
        if token is not None:
            self.begin_col = token.col
            self.end_col = token.col
            self.required = (token.option == 'required')

        # 求值缓存
        self.cache_eval = None
        self.cache_cell_row = None

    # 添加元素项，数组类型name为None
    def add_member(self, name, pt):
        self.members.append((name, pt))

    def get_member(self, name):
        for key, value in self.members:
            if key == name:
                return value
        return None

    def is_all_member_nil(self, row_cells):
        for _, m in self.members:
            if m.eval(row_cells) != 'nil':
                return False
        return True

    def eval(self, cell_row):
        if self.cache_eval == cell_row:
            return self.cache_eval

        eval_str = 'nil'
        # 单列类型空值处理
        if (self.type != type_array and self.type != type_dict) and cell_row[self.begin_col].value == '':
            eval_str = 'nil'
        else:
            if self.type == type_int:
                val = cell_row[self.begin_col].value
                i = int(val)
                eval_str = str(i)
            elif self.type == type_string:
                val = cell_row[self.begin_col].value
                if val == '':
                    eval_str = 'nil'
                else:
                    eval_str = add_quout(val)
            elif self.type == type_number:
                val = cell_row[self.begin_col].value
                eval_str = str('%g' % val)
            elif self.type == type_bool:
                val = cell_row[self.begin_col].value
                lower_str = str(val).lower()
                if lower_str == '0' or lower_str == 'false':
                    eval_str = 'false'
                else:
                    eval_str = 'true'
            elif self.type == type_table:
                val = cell_row[self.begin_col].value
                eval_str = '{' + val + '}'
            elif self.type == type_function:
                val = cell_row[self.begin_col].value
                eval_str = '%s return %s end' % (self.token.decl_type, val)
            elif self.type == type_array:
                all_member_nil = self.is_all_member_nil(cell_row)
                # 全部子项为空，且该节点为可选类型，则不输出
                if all_member_nil and not self.required:
                    eval_str = 'nil'
                elif all_member_nil:
                    eval_str = '{}'
                else:
                    eval_str = '{'
                    mcount = len(self.members)
                    for i in range(mcount):
                        (_, m) = self.members[i]
                        eval_str += m.eval(cell_row)
                        eval_str += ','
                    if eval_str.endswith(','):
                        eval_str = eval_str[:-1]
                    eval_str += '}'
            elif self.type == type_dict:
                all_member_nil = self.is_all_member_nil(cell_row)
                # 全部子项为空，且该节点为可选类型，则不输出
                if all_member_nil and not self.required:
                    eval_str = 'nil'
                elif all_member_nil:
                    eval_str = '{}'
                else:
                    eval_str = '{'
                    mcount = len(self.members)
                    for i in range(mcount):
                        (key, m) = self.members[i]
                        meval = m.eval(cell_row)
                        if meval != 'nil':
                            eval_str += '%s=%s' % (key, meval)
                            eval_str += ','
                    if eval_str.endswith(','):
                        eval_str = eval_str[:-1]
                    eval_str += '}'
            else:
                eval_error('无法求值列%s未知类型%s' % (to_xls_col(self.begin_col), str(self.type)))

        # 空值检查
        if self.required and eval_str == 'nil':
            eval_error('列%s项%s类型节点不能为空' % (to_xls_col(self.begin_col), str(self.type)))

        self.cache_cell_row = cell_row 
        self.cache_eval = eval_str
        return eval_str


# 解析器
class SheetParser:
    def __init__(self, ts):
        self.tokens = ts
        self.pos = 0

        # 配置符合类型对应的解析函数
        self.parser_cfg = {
            type_array: self.parse_array_node,
            type_dict: self.parse_dict_node,
        }

        root_node = NodeParser(type_dict, None)
        root_node.begin_col = self.cur_token().col
        self.parse_dict_node(root_node)
        root_node.end_col = self.tokens[self.pos-1].col
        self.root_parser = root_node

    # 取得当前读取位置的符号
    def cur_token(self):
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    # 读取头前进
    def skip_token(self):
        self.pos += 1

    # 解析简单类型
    def parse_simple_node(self):
        cur = self.cur_token()
        pt = NodeParser(cur.decl_type, cur)
        pt.begin_col = cur.col
        pt.end_col = cur.col
        return pt

    # 解析复合类型
    def parse_complex_node(self, pt):
        cur = self.cur_token()
        for k, v in complex_token_def.items():
            if v[0] == cur.decl_type:
                value = NodeParser(k, cur)
                value.begin_col = cur.col
                self.skip_token()
                self.parser_cfg[k](value)
                return value
        parse_error('解析列%d的%s类型元素时,遇到了位于列%d的意外的符号\'%s\'' % (pt.begin_col, pt.type, cur.col, str(cur)))
        return None

    # 解析数组类型
    def parse_array_node(self, arr_node):
        cur = self.cur_token()
        (_, end_token) = complex_token_def[type_array]
        while cur is not None:
            if cur.decl_type == end_token:
                arr_node.end_col = cur.col
                break

            if cur.decl_type == '':
                parse_error('列%d项%s没有声明类型' % (cur.col, str(cur.name)))
                break
            elif is_simple_type(cur.decl_type):
                value = NodeParser(cur.decl_type, cur)
                self.skip_token()
            elif cur.decl_type.startswith(type_function):
                value = NodeParser(type_function, cur)
                self.skip_token()
            else:
                value = self.parse_complex_node(arr_node)
                self.skip_token()
            if value is not None:
                arr_node.add_member(cur.name, value)
            cur = self.cur_token()

    # 解析字典类型
    def parse_dict_node(self, dict_node):
        cur = self.cur_token()
        (_, end_token) = complex_token_def[type_dict]
        while cur is not None:
            if cur.decl_type == end_token:
                dict_node.end_col = cur.col
                break

            if cur.name == '':
                parse_error('解析列%d的%s类型元素时,遇到位于列%d的元素缺少变量名' % (dict_node.begin_col, dict_node.type, cur.col))
                break

            if cur.decl_type == '':
                parse_error('列%d项%s没有声明类型' % (cur.col, str(cur.name)))
                break
            elif is_simple_type(cur.decl_type):
                value = NodeParser(cur.decl_type, cur)
                self.skip_token()
            elif cur.decl_type.startswith(type_function):
                value = NodeParser(type_function, cur)
                self.skip_token()
            else:
                value = self.parse_complex_node(dict_node)
                self.skip_token()
            if value is not None:
                # 路径变量需要解析取得操作对象
                path_id = cur.name.split('.')
                path_len = len(path_id)
                if path_len > 1:
                    last_node = dict_node
                    for i in range(path_len-1):
                        key = path_id[i]
                        last_node = last_node.get_member(key)
                        if last_node is None or last_node.type != type_dict:
                            parse_error('path_id(%s) is invalid' % cur.name)
                            break
                    last_node.add_member(path_id[path_len-1], value)
                else:
                    dict_node.add_member(cur.name, value)
            cur = self.cur_token()


# 读取xls文件内容，并过滤注释行
def read_sheets_from_xls(file_path):
    workbook = xlrd.open_workbook(file_path)
    sheets = []
    for sheet in workbook.sheets():
        if sheet.ncols <= 0:
            continue
        cells = []
        for y in range(0, sheet.nrows):
            # 过滤全空白行
            all_empty = True
            for v in sheet.row_values(y):
                if v != '':
                    all_empty = False
                    break
            if all_empty:
                continue
            text = sheet.cell_value(y, 0)
            # 过滤注释行
            if isinstance(text, unicode) and text.startswith('//'):
                continue
            cells.append(sheet.row(y))
        if len(cells) > 0:
            sheets.append((sheet.name, cells))
    return sheets


def build_parser_tree(sheet_cells):
    ts = []
    for col in range(len(sheet_cells[0])):
        option = sheet_cells[0][col].value
        decl_type = sheet_cells[1][col].value
        name = sheet_cells[2][col].value
        t = Token(option, decl_type, name, col)
        ts.append(t)
    sp = SheetParser(ts)
    return sp.root_parser


def xls_to_lua(file_path, out_file_path):
    sheets = read_sheets_from_xls(file_path)    # 过滤注释行
    for name, cells in sheets:
        root_parser = build_parser_tree(cells)
        _, key_node = root_parser.members[0]
        for y in range(3, len(cells)):
            row = cells[y]
            print '[%s]=%s,' % (key_node.eval(row), root_parser.eval(row))

if __name__ == '__main__':
    xls_to_lua('test.xlsx', '')




