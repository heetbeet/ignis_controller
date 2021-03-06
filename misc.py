#%%
import time
from datetime import datetime
import os
from types import SimpleNamespace

import minimalmodbus
import pythoncom
import win32api
import win32com.client
import traceback

alph = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
num2col = [i for i in alph] + [i+j for i in alph for j in alph]


def is_interactive():
    import __main__ as main
    return not hasattr(main, '__file__')


def try_thrice(f, *args, errors_list=None, **kwargs):
    """
    Try to run a function three times before giving up

    >>> count = {'i':0}
    >>> # noinspection PyUnresolvedReferences
    ... def func():
    ...     count['i'] += 1
    ...     assert count['i'] >= 3

    >>> try_thrice(func)

    """
    if errors_list is None:
        errors_list = Exception
    else:
        errors_list = tuple(errors_list)

    for i in range(2):
        # noinspection PyBroadException
        try:
            return f(*args, **kwargs)
        except errors_list:
            time.sleep(0.05)

    return f(*args, **kwargs)


def spread_iterator():
    for moniker in pythoncom.GetRunningObjectTable():
        try:
            # Workbook implements IOleWindow so only consider objects implementing that
            window = moniker.BindToObject(pythoncom.CreateBindCtx(0), None, pythoncom.IID_IOleWindow)
            disp = window.QueryInterface(pythoncom.IID_IDispatch)


            # Get a win32com Dispatch object from the PyIDispatch object as it's
            # easier to work with.
            book = win32com.client.Dispatch(disp)

        except pythoncom.com_error:
            # Skip any objects we're not interested in
            continue

        try:
            book.Sheets(1) #Object is a book with sheets
        except:
            continue
            
        bookname = moniker.GetDisplayName(pythoncom.CreateBindCtx(0), None)

        yield bookname, book

def get_ignis_spreadsheet():
    for bookname, book in spread_iterator():
        print('Test workbook: ', bookname)

        inputs  = [i for i in book.Sheets if i.Name.lower() == 'inputs']
        outputs = [i for i in book.Sheets if i.Name.lower() == 'outputs']

        if len(inputs) and len(outputs):
            print('Yes -->', bookname)
            return book, inputs[0], outputs[0]
        
def get_spreadsheet_by_name(spreadname):
    for bookname, book in spread_iterator():
        print('Test workbook: ', bookname)
        fname = os.path.split(bookname)[-1].lower()

        fexts = ['.xls', '.csv', '.txt']
        for fext in fexts:
            if fext in fname:
                fname = fext.join(fname.split(fext)[:-1])
        if fname == spreadname.lower():
            return book


def force_int(s):
    s = str(s)
    if "." in s:
        val = float(s)
    else:
        val = int(s, 0)

    return int(val)


def str2bits(s):
    result = []
    for c in s:
        bits = bin(ord(c))[2:]
        bits = '00000000'[len(bits):] + bits
        result.extend([int(b) for b in bits])
    return result

def bits2str(bits):
    bitgroups = [bits[i:i+8] for i in range(0,len(bits),8)]
    int_list = []
    for bit in bitgroups:
        int_list.append(0)
        for i, val in enumerate(bit[::-1]):
            int_list[-1] += (2**(i))*bool(val)
    str_out = ''.join([chr(i) for i in int_list])
    return str_out

def bits2int(bits):
    out_int = 0
    for i, val in enumerate(bits[::-1]):
        out_int += (2**(i))*bool(val)
    return out_int

class timeStrober:
    def __init__(self, inpstr):
        self.set_timings(inpstr)
    
    def set_timings(self, inpstr):
        try:
            inpstr*1.0
        except: pass
        else:
            inpstr = 'on' if inpstr else 'off'
            
        inpstr = inpstr.lower().strip()

        if inpstr.startswith('t'):
            self.pperiod, self.pwidth = time.time(), float(inpstr[1:].strip())

        elif inpstr.startswith('s'):
            self.pperiod, self.pwidth = (float(inpstr[1:].split(',')[0].strip()),
                                         float(inpstr[1:].split(',')[1].strip()) )
            if self.pperiod == 0:
                self.pperiod += 0.05
        elif inpstr == 'on':
            self.pperiod, self.pwidth = time.time(), time.time()

        elif inpstr == 'off':
            self.pperiod, self.pwidth = time.time(), 0

        else:
            raise('Error timestrobe inputs.')
        
    def is_on(self):
        now = time.time()
        if now - int(now/self.pperiod)*self.pperiod < self.pwidth:
            return True
        else:
            return False

def get_instruments(comname, nr_of_devices):
    import minimalmodbus

    minimalmodbus.BAUDRATE = 9600
    minimalmodbus.CLOSE_PORT_AFTER_EACH_CALL = False
    instances = []
    for i in range(1, nr_of_devices+1):
        instances.append(minimalmodbus.Instrument(comname, i))
    
    return instances

def write_to_inst(ins, value, reg=320):
    if isinstance(value, list) or isinstance(value, tuple):
        value = bits2int(value[::-1])

    try:
        ins.write_register(reg, value)
        return True
    except OSError:
        return False
    
def get_mode_limit(wb):
    results_sheet  = [i for i in wb.Sheets if i.Name.lower() == 'results'][0]
    compiled_sheet  = [i for i in wb.Sheets if i.Name.lower() == 'compiled data'][0]
    return [results_sheet.Range("AW3").Value,
            compiled_sheet.Range("CX4").Value]

class test_writer:
    def __init__(self):
        self.curr_line = 6
    
    def do_readings(self, inputs_sheet, testing_sheet):
        for i in range(self.curr_line,60000):
            if not inputs_sheet.Range('A'+str(i)).Value:
                self.curr_line = i
                break
                
        cells = 'A%d:CC%d'%(self.curr_line, self.curr_line)
        inputs_sheet.Range(cells).Value = testing_sheet.Range(cells).Value


class inputs_writer:
    def __init__(self):
        self.curr_line = 6
        self.sensitivity_col = None
        self.results_sheet = None
        self.inputs_sheet = None
    
    def do_readings(self, wb, inputs_sheet, ins1, ins2, ins3, ins4, ins5, ins6, ins7):
        if self.sensitivity_col is None:
            self.inputs_sheet   = [i for i in wb.Sheets if i.Name.lower() == 'inputs' ][0]
            self.results_sheet  = [i for i in wb.Sheets if i.Name.lower() == 'results'][0]
            for i, val in enumerate(self.results_sheet.Range("5:5").Value[0]):
                if str(val).lower().strip() == 'sensitivity':
                    self.sensitivity_col = num2col[i]
        
        for i in range(self.curr_line,60000):
            if not inputs_sheet.Range('A'+str(i)).Value:
                self.curr_line = i
                break
        try:        
            data =(
                [str(datetime.now())]+
                ins2.read_registers(512, 8)+
                ins2.read_registers(520, 8)+
                ins3.read_registers(512, 8)+
                ins3.read_registers(520, 8)+
                str2bits(ins1.read_string(320,1))[::-1][:8]+
                ins4.read_registers(512, 8)+
                ins4.read_registers(520, 8)+
                ins5.read_registers(512, 8)+
                ins5.read_registers(520, 8)+
                str2bits(ins6.read_string(320,1))[::-1][:8]+
                [None]*16
                #ins7.read_registers(512, 8)+
                #ins7.read_registers(520, 8)
            )
        except:
            return False

        #Some excel conversions ans lookups
        alph = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        xl = alph+[i+j for i in alph for j in alph]
        
        row = self.curr_line
        
        col0 = xl[0]           #datalines from the instuments
        col1 = xl[len(data)-1]
        
        col2 = xl[len(data)]  #extra feedback from excel
        col3 = xl[len(data)+1]
        col4 = xl[len(data)+2]
        
        self.inputs_sheet.Range(f'{col3}{row}:{col4}{row}').Value = get_mode_limit(wb)
        self.inputs_sheet.Range(f'{col2}{row}').Value = self.results_sheet.Range('%s%d'%(self.sensitivity_col, self.curr_line-1))
        self.inputs_sheet.Range(f'{col0}{row}:{col1}{row}').Value = data
        
        return True


class inputs_writer_icarus:
    def __init__(self):
        self.curr_line = 6
        self.sensitivity_col = None
        self.results_sheet = None
        self.inputs_sheet = None

    def do_readings(self, wb, inputs_sheet, ins1, ins2, ins3, ins4):
        if self.sensitivity_col is None:
            self.inputs_sheet = [i for i in wb.Sheets if i.Name.lower() == 'inputs'][0]
            self.results_sheet = [i for i in wb.Sheets if i.Name.lower() == 'results'][0]
            for i, val in enumerate(self.results_sheet.Range("5:5").Value[0]):
                if str(val).lower().strip() == 'sensitivity':
                    self.sensitivity_col = num2col[i]

        for i in range(self.curr_line, 60000):
            if not inputs_sheet.Range('A' + str(i)).Value:
                self.curr_line = i
                break

        def _read():
            none_line = [None] * 8

            data_date = [str(datetime.now())]  # 0
            data2 = ins2.read_registers(512, 8) if ins2 is not None else none_line  # 1-8
            data3 = ins3.read_registers(512, 8) if ins3 is not None else none_line  # 9-16
            data4 = ins4.read_registers(1, 8) if ins4 is not None else none_line  # 17-24
            data1 = str2bits(ins1.read_string(320, 1))[::-1][:8] if ins1 is not None else none_line  # 25-32
            data = (data_date + data2 + data3 + data4)

            return SimpleNamespace(
                data1=data1,
                data2=data2,
                data3=data3,
                data4=data4,
                data=data
            )

        try:
            p = try_thrice(_read, errors_list=[minimalmodbus.NoResponseError])
        except Exception as e:
            traceback.print_exc()
            return False

        # Some excel conversions and lookups
        alph = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        xl = alph + [i+j for i in alph for j in alph]

        row = self.curr_line

        col0 = xl[0]  # datalines from the instuments
        col1 = xl[len(p.data) - 1]

        self.inputs_sheet.Range(f'{col0}{row}:{col1}{row}').Value = p.data
        self.inputs_sheet.Range(f'AI{row}:AP{row}').Value = p.data1

        return True