# coding:utf-8
import inspect
import re
import xlrd

# 定义符号
type_array = 'array'
type_dict = 'dict'
type_int = 'int'
type_number = 'number'
type_string = 'string'
type_expr = 'expr'

# 定义简单类型
simple_type_def = {
    type_int: True,
    type_number: True,
    type_string: True,
}

# 定义复合类型
complex_token_def = {
    type_array: ('array<', '>'),
    type_dict: ('dict<', '>'),
}


# 判断是否简单类型
def is_simple_type(ty):
    return ty in simple_type_def

def is_single_col_complex_type(ty):
    for k,v in complex_token_def.items():
        if ty == v[0] + v[1]:
            return k

# 将整数转换为excel的列
def to_xls_col(num):
    A = ord('A')
    str = ''
    tmp = num
    while True:
        factor = tmp / 26
        remain = tmp % 26
        tmp = factor
        str = chr(remain + A) + str
        if factor == 0:
            break
    return str


# 读取xls文件内容，并过滤注释行
def open_xls(filepath):
    workbook = xlrd.open_workbook(filepath)
    sheets = workbook.sheets()
    cells = []
    for sheet in sheets:
        if sheet.ncols <= 0:
            continue
        for y in range(0, sheet.nrows):
            text = sheet.cell_value(y, 0)
            if isinstance(text, unicode) and text.startswith('//'):
                continue
            cells.append(sheet.row(y))
    return cells


# 表头符号，每个符号由类型和名字组成，用于构造表格数据结构
class Token:
    def __init__(self, ty, iden, col):
        self.ty = ty
        self.id = iden
        self.col = col

    def __str__(self):
        if self.ty == '':
            return self.id
        else:
            return '%s:%s' % (self.id, self.ty)


# 表格数据结构，基于token流构造
class Proto:
    def __init__(self, type):
        self.type = type
        self.members = []
        self.begin_col = -1
        self.end_col = -1

    # 添加元素项，数组类型name为None
    def add_member(self, name, pt):
        self.members.append((name, pt))

    def get_member(self, name):
        for key,value in self.members:
            if key == name:
                return value
        return None

    def colstr(self):
        if self.begin_col == self.end_col:
            return '(col %s)' % to_xls_col(self.begin_col)
        else:
            return '(col %s,%s)' % (to_xls_col(self.begin_col), to_xls_col(self.end_col))

    # 打印输出
    def tostr(self, identity):
        result = ''
        if self.type == type_array:
            result += self.type
            result += self.colstr()
            result += '[\n'
            for i in range(len(self.members)):
                (_, pt) = self.members[i]
                result += '\t' * (identity+1)
                result += pt.tostr(identity+1)
                result += ','
                result += '\n'
            result += '\t' * identity
            result += ']'
        elif self.type == type_dict:
            result += self.type
            result += self.colstr()
            result += '{\n'
            for i in range(len(self.members)):
                (name, pt) = self.members[i]
                result += '\t' * (identity+1)
                result += name
                result += pt.colstr()
                result += ': '
                result += pt.tostr(identity+1)
                result += ','
                result += '\n'
            result += '\t' * identity
            result += '}'
        else:
            result += self.type
            result += self.colstr()
        return result

    def __str__(self):
        return self.tostr(0)


class Expr(Proto):
    def __init__(self):
        Proto.__init__(self, type_expr)
        self.argument = []

    def add_argment(self, arg):
        self.argument.append(arg)

    def tostr(self, identity):
        result = 'expr('
        arg_count = len(self.argument)
        for i in range(arg_count):
            arg = self.argument[i]
            result += arg
            if i < arg_count - 1:
                result += ','
        result += ')'
        return result + self.colstr()


# 解析器
class Parser:
    def __init__(self, ts):
        self.tokens = ts
        self.pos = 0

        # 配置符合类型对应的解析函数
        self.parser_cfg = {
            type_array: self.parse_array,
            type_dict: self.parse_dict,
        }

        root_node = Proto(type_dict)
        root_node.begin_col = self.cur_token().col
        self.parse_dict(root_node)
        root_node.end_col = self.tokens[self.pos-1].col
        self.proto_node = root_node

    # 取得当前读取位置的符号
    def cur_token(self):
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    # 读取头前进
    def skip_token(self):
        self.pos += 1

    # 输出解析错误信息并退出程序
    def parse_error(self, msg):
        print '[parse error]%s' % msg
        # stack = inspect.stack()
        # print 'stack='
        # for level in stack:
        #     print level
        exit(1)

    # 解析简单类型
    def parse_simple_value(self):
        cur = self.cur_token()
        pt = Proto(cur.ty)
        pt.begin_col = cur.col
        pt.end_col = cur.col
        return pt

    # 解析复合类型
    def parse_complex_value(self, pt):
        cur = self.cur_token()
        for k,v in complex_token_def.items():
            if v[0] == cur.ty:
                value = Proto(type_array)
                value.begin_col = cur.col
                self.skip_token()
                self.parser_cfg[k](value)
                return value
        self.parse_error('解析列%d的%s类型元素时,遇到了位于列%d的意外的符号\'%s\'' % (pt.begin_col, pt.type, cur.col, str(cur)))
        return None

    # 解析表达式类型
    def parse_expr(self):
        cur = self.cur_token()
        pt = Expr()
        pt.begin_col = cur.col
        pt.end_col = cur.col
        ty = cur.ty
        if ty != type_expr:
            m = re.match('expr\((.+)\)', ty)
            if m is not None:
                arg_str = m.group(1)
                for arg in arg_str.split(','):
                    pt.add_argment(arg)
        return pt

    # 解析数组类型
    def parse_array(self, arr):
        cur = self.cur_token()
        (_, end_token) = complex_token_def[type_array]
        while cur is not None:
            if cur.ty == end_token:
                arr.end_col = cur.col
                break

            value = None
            if cur.ty == '':
                self.parse_error('列%d项%s没有声明类型' % (cur.col, str(cur.id)))
                break
            elif is_simple_type(cur.ty):
                value = self.parse_simple_value()
                self.skip_token()
            else:
                # 解析表达式类型
                if cur.ty.startswith(type_expr):
                    value = self.parse_expr()
                else:
                    fold_ty = is_single_col_complex_type(cur.ty)
                    if fold_ty is not None:
                        value = Proto(fold_ty)
                        value.begin_col = cur.col
                        value.end_col = cur.col
                    else:
                        value = self.parse_complex_value(dict)
                self.skip_token()
            if value is not None:
                arr.add_member(None, value)
            cur = self.cur_token()

    # 解析字典类型
    def parse_dict(self, dict):
        cur = self.cur_token()
        (_, end_token) = complex_token_def[type_dict]
        while cur is not None:
            if cur.ty == end_token:
                dict.end_col = cur.col
                break

            value = None
            if cur.id == '':
                self.parse_error('解析列%d的%s类型元素时,遇到位于列%d的元素缺少变量名' % (dict.begin_col, dict.type, cur.col))
                break

            value = None
            if cur.ty == '':
                self.parse_error('列%d项%s没有声明类型' % (cur.col, str(cur.id)))
                break
            elif is_simple_type(cur.ty):
                value = self.parse_simple_value()
                self.skip_token()
            else:
                # 解析表达式类型
                if cur.ty.startswith(type_expr):
                    value = self.parse_expr()
                else:
                    fold_ty = is_single_col_complex_type(cur.ty)
                    if fold_ty is not None:
                        value = Proto(fold_ty)
                        value.begin_col = cur.col
                        value.end_col = cur.col
                    else:
                        value = self.parse_complex_value(dict)
                self.skip_token()
            if value is not None:
                # 路径变量需要解析取得操作对象
                idpath = cur.id.split('.')
                length = len(idpath)
                if length > 1:
                    last_pt = dict
                    for i in range(length-1):
                        key = idpath[i]
                        last_pt = last_pt.get_member(key)
                        if last_pt is None:
                            self.parse_error('idpath(%s) is invalid' % cur.id)
                            break
                    last_pt.add_member(idpath[length-1], value)
                else:
                    dict.add_member(cur.id, value)
            cur = self.cur_token()

if __name__ == "__main__":
    cells = open_xls('test.xlsx')    # 过滤注释行
    ts = []
    for col in range(0, len(cells[0])):
        ty = cells[0][col].value
        iden = cells[1][col].value
        t = Token(ty, iden, col)
        ts.append(t)
    ps = Parser(ts)
    print ps.proto_node


