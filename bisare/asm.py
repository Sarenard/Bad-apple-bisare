#!/usr/bin/env python3

import argparse
import math
import os
import sys
import re

# known mnemonics
fmt_00     = ["jump", "call"]

# ALU operations (warning: index in this list is our 'function' code)
fmt_01 = ["copy", "add", "sub", "or", "and", "xor", "lsl", "lsr",
          "asr", "smull", "smulh", "umull", "umulh", "div", "mod"]

# Memory instructions (0 to 3) or miscelaneous
fmt_10 = ["store", "load", "push", "pop",
          "ret","reti","swi","dint","eint"] # note COPY to/from SP is handled separately

fmt_11 = ["skip"]

cond_codes = {"ifeq":0b0000,
              "ifne":0b0001,
              "iflt":0b1000,
              "ifge":0b1001,
              "ifgt":0b1010,
              "ifle":0b1011,
              "ifult":0b1100,
              "ifuge":0b1101,
              "ifugt":0b1110,
              "ifule":0b1111,
              }

fmt_pseudo = ["halt", "let", "nop", "not", "skipto"]

gp_reg_names = ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
                "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]

# current location in the input source file
linenum=-1

def error(message,lnum=None):
    # most error messages complain about the current line.
    # however when resolving label addresses we show the original instruction

    if lnum == None:
        lnum = linenum
    try:
        print(f"{asmfilename}:{lnum}: {message}")
        print(f"line {lnum}: {asmlines[lnum]}")
        # raise RuntimeError # uncomment this line to display a stack trace (useful to debug the assembler itself)
    except:
        print(message)
        raise
    sys.exit(1)

def parse_integer_literal(text, check17bits=True):
    if len(text) == 0:
        error(f"Empty string not allowed here")
    if " " in text:
        error(f"No whitespace allowed in integer constant: '{text}'")
    if "--" in text:
        error(f"Duplicate sign: '{text}'")
    if "+" in text:
        error(f"Plus sign not allowed here: '{text}'")
    elif text[:3] == '-0x':
        if check17bits and len(text) != 7:
            error(f"Hex constant must be written as 4 digits: '{text}'")
        value=int(text,16)
    elif text[:2] == '0x':
        if check17bits and len(text) != 6:
            error(f"Hex constant must be written as 4 digits: '{text}'")
        value=int(text,16)
    elif all([letter in "-1234567890" for letter in text]):
        value=int(text,10)
    else:
        error(f"Cannot understand integer constant: '{text}'")
        
    if check17bits and not (-0xFFFF <= value <= 0xFFFF):
        error(f"Value too big for litteral constant: '{text}'")
    return value
    

def parse_jump_distance(text):
    """Recognize +12, -4, etc. Choke on numbers wider than signed 29-bits"""
    sign = 1
    if text[0]=='-':
        sign = -1
        text=text[1:]
    distance=sign*parse_integer_literal(text)
    if distance < -(1<<28) or distance >= (1<<28):
        error(f'Jump distance is too large: {text}')
    return distance

def parse_memory_operand(text):
    """Recognize [Ra+Rb] or [Ra + Cst] or [Ra - Cst]  or just [Ra]
    
       returns a 3-tuple: Ra (int), Rb (int or None), Cst (int or None) 
    """
    if text[0] != "[" or text[-1] != "]":
        error("invalid syntax for memory operand '{text}'")
    text=text[1:-1].strip()

    if "+" not in text and "-" not in text:
    # easy case e.g. [r3] without offset
        return parse_gp_register_name(text), None, 0

    if text.count('+') + text.count('-') > 1:
        error(f"Too many signs: '{text}'")

    if '+' in text:
        pos    = text.index('+')
        sign = 1
    else:
        pos = text.index('-')
        sign = -1

    text_rx = text[:pos].strip()
    text_op2 = text[pos+1:].strip()

    reg = parse_gp_register_name(text_rx)
    if parse_gp_register_name(text_op2, noerror=True) is not None:
        if sign == -1:
            error(f"register-register subtraction not allowed here '[{text}]'")
        return parse_gp_register_name(text_rx), parse_gp_register_name(text_op2), None
    else:
        return parse_gp_register_name(text_rx), None, sign*parse_integer_literal(text_op2)


forbidden_labels = fmt_00 + fmt_01 + fmt_10 + fmt_11 + list(cond_codes.keys()) + fmt_pseudo + gp_reg_names


def parse_label(text, noerror=False):
    text=text.strip()
    m = re.match('[a-zA-Z_][a-zA-Z0-9_]*$',text)
    #if ( m is None or text in type1+type2+type3+type4+type_pseudo+reg_names+alias_names):
    #TODO: match against reserved names (instructions, reg names, etc)
    if m is None or text in forbidden_labels:
        if noerror: return None
        error(f"Invalid label name: '{text}'")
    return text

def parse_gp_register_name(text, noerror=False):
    """Interpret a string as a register number: r1 -> 1, r2 -> 2 ... r15 -> 15"""
    if text not in gp_reg_names:
        if noerror: return None
        error(f"Incorrect general-purpose register: '{text}'")
    return gp_reg_names.index(text)

def check_generic_args(line,expected_arg_count):
    """check the number of arguments in 'line', return them as a list of strings"""
    return Instruction(line).check_args(expected_arg_count)

class Instruction():
    def __init__(self,line):
        self.linenum = linenum

        # Tokenisation and related checks
        line=line.strip()
        if " " in line:
            firstspace=line.index(" ")
            self.words = [line[:firstspace]]
            rest = line[firstspace+1:].strip()
        else:
            self.words=[line]
            rest = None
            
        if self.words[0] not in fmt_00+fmt_01+fmt_10+fmt_11+fmt_pseudo:
            error("Invalid instruction name '"+self.words[0]+"'")

        if rest:
            tokens= [ w.strip() for w in rest.split(" ")]
            self.words+= [s for s in tokens if s] # remove empty tokens

    def check_args(self,expected_arg_count):
        argc = len(self.words)-1
        if   argc < expected_arg_count:
            error(f"Not enough operands for '{self.words[0]}'")
        elif argc > expected_arg_count:
            error(f"Too many operands for '{self.words[0]}'")
        return self.words[1:]

    def encode(self):
        raise NotImplementedError("concrete subclasses must implement this method")

class Instruction00(Instruction): # jump and call
    def __init__(self,line):
        super().__init__(line)
        if self.words[0] == "halt":
            self.check_args(0) # TODO: test various "halt op"
            self.typebit = 0
            self.offset = 0 # offset 'd' is a number of instructions
            self.dest = None
            return
        self.dest = None
        if label := parse_label(self.words[1], noerror=True):
            self.offset = None
            self.dest = label
        else:
            self.dest = None
            self.offset = parse_jump_distance(self.words[1])

        self.typebit = 0 if self.words[0] == "jump" else 1
        
    def encode(self):
        if self.dest is not None:
            try:
                dest_addr = exe.symbols[self.dest]
            except KeyError:
                error(f"Cannot resolve symbol: '{self.dest}'",self.linenum)
            self.offset = (dest_addr - self.addr)//4
            
        assert -2**28 <= self.offset < 2**28
        return self.typebit<<29 | self.offset % 2**29 # two's complement on 29 bits


class Instruction123(Instruction):
    def __init__(self,line):
        super().__init__(line)
        self.fmt=None
        self.function=None
        self.rd=None
        self.rx=None
        # I'm removing the "immediate" flag, in favour of another
        # convention: either 'ry' or 'constant' must exist, and not both
        self.ry=None
        self.constant=None
        self.sign=None # not sure about this one either

        self.text=line # source code
        
    def encode(self):
        if self.ry is None and self.constant is None:
            raise RuntimeError("ASM BUG: no second operand: "+" ".join(self.words))
        if self.ry is not None and self.constant is not None:
            raise RuntimeError ("ASM BUG: multiple second operand: "+" ".join(self.words))

        code = self.fmt<<30 | self.function<<24 | self.rd<<20 | self.rx<<16
        
        if self.constant is not None:
            #print(f'{self.addr:04x}:ENCODE fmt={self.fmt:02b} s={self.sign} i=1 function={self.function:04b} d={self.rd} x={self.rx} cst={self.constant%(2**16)} for `{" ".join(self.words)}`')
            return  code | self.sign<<29 | 1<<28 | self.constant % (2**16)
        else:
            #print(f'{self.addr:04x}:ENCODE fmt={self.fmt:02b} s=0 i=0 function={self.function:04b} d={self.rd} x={self.rx} y={self.ry}')
            return  code | self.ry<<12
    def __str__(self):
        ret = []
        for attr in ["fmt", "function", "rd", "rx", "ry", "constant", "sign"]:
            try:
                ret.append(attr+'='+str(self.__getattribute__(attr)))
            except:
                ret.append(attr+'=?')
        return self.__class__.__name__+'('+", ".join(ret)+', text="'+self.text+'")'
    def __repr__(self):
        return str(self)

class Instruction01(Instruction123): # arithmetic and logic operations
    def __init__(self,line):
        super().__init__(line)
        self.fmt=0b01
        self.function=fmt_01.index(self.words[0])

        if self.words[0] == "copy":
            rest=check_generic_args(line, 2)
            self.rd = parse_gp_register_name(rest[0])
            self.rx = 0
        else:
            rest=check_generic_args(line,3)
            self.rd = parse_gp_register_name(rest[0])
            self.rx = parse_gp_register_name(rest[1])

        ry = parse_gp_register_name(rest[-1], noerror=True)
        if ry is not None:
                self.ry = ry
        else:
            # TODO: here we should check "assembler syntax conventions" as per isa card
            if rest[-1][0] == '-':
                self.sign=1
                self.constant = parse_integer_literal(rest[-1])
            else:
                self.sign=0
                self.constant = parse_integer_literal(rest[-1])
            
class Instruction10(Instruction123): # memory instructions
    def __init__(self, line):
        super().__init__(line)
        self.fmt=0b10

        if self.words[0] == "copy": # copy to/from SP
            rest=check_generic_args(line, 2)
            if rest[0] == "sp": # special case: copy SP, Op2
                self.function = 0b1110
                self.rd=self.rx=0 # ignored operands for this instruction
                ry = parse_gp_register_name(rest[-1], noerror=True)
                if ry is not None:
                    self.ry = ry
                else:
                    # TODO: here we should check "assembler syntax conventions" as per isa card
                    if rest[-1][0] == '-':
                        self.sign=1
                        self.constant = parse_integer_literal(rest[-1])
                    else:
                        self.sign=0
                        self.constant = parse_integer_literal(rest[-1])
            elif rest[1] == "sp": # special case: copy Rd, SP
                raise NotImplementedError
            else:
                error('invalid syntax')

        elif self.words[0] == "store":
            self.function=0
            memop, rd = check_generic_args(line, 2)
            self.rx,self.ry,self.constant=memop=parse_memory_operand (memop)
            self.rd=parse_gp_register_name(rd)
            self.sign = 1 if self.constant and self.constant<0 else 0

        elif self.words[0] == "load":
            self.function = 1
            rd, memop = check_generic_args(line,2)
            self.rx,self.ry,self.constant=memop=parse_memory_operand (memop)
            self.rd=parse_gp_register_name(rd)
            self.sign = 1 if self.constant and self.constant<0 else 0

        elif self.words[0] == "push":
            self.function = 2
            op2 = check_generic_args(line,1)[0]
            if parse_gp_register_name(op2, noerror=True) is not None:
                self.constant = None
                self.ry=parse_gp_register_name(op2, noerror=True)
            else:
                self.ry=None
                self.constant=parse_integer_literal(op2)
            self.rx=self.rd=0 # dummy value to please `encode`
            self.sign = 1 if self.constant and self.constant<0 else 0 # to please encode

        elif self.words[0] == "pop":
            self.function = 3
            rd_text=check_generic_args(line,1)[0]
            self.rd = parse_gp_register_name(rd_text)
            self.rx=self.ry=0 # dummy values to please `encode`

        elif self.words[0] == "ret":
            self.function = 8 # 0b1000
            self.rd=self.rx=self.ry=0 
        elif self.words[0] == "reti":
            self.function = 9 # 0b1001
            self.rd=self.rx=self.ry=0 
        elif self.words[0] == "swi":
            self.function = 10 # 0b1010
            x_text=check_generic_args(line,1)[0]
            self.rx=parse_integer_literal(x_text)
            assert 0 <= self.rx < 16
            self.rd=self.ry=0 
        elif self.words[0] == "dint":
            self.function = 12 # 0b1100
            self.rd=self.rx=self.ry=0 
        elif self.words[0] == "eint":
            self.function = 13 # 0b1101
            self.rd=self.rx=self.ry=0

        elif self.words[0] == "copy":
            check_generic_args(line,2)
            if self.words[2] == 'sp': # copy Rd SP
                self.function=14 # 0b1110
                self.rd=parse_gp_register_name(self.words[1])
                self.rx=self.ry=0
            elif self.words[1] == 'sp': # copy SP Op2
                self.function=15 # 0b1111
                ry = parse_gp_register_name(self.words[2], noerror=True)
                if ry is not None:
                    self.ry = ry
                else:
                    self.constant=parse_integer_literal(self.words[2])
                self.rx=self.rd=0
                self.sign=0 # XXX TODO FIXME
            else:
                error('invalid syntax')
            
        
        
        else:
            raise NotImplementedError

class Instruction11(Instruction123):
    def __init__(self,line):
        # we're skipping the call to super().__init__ here since our
        # syntax is very different. not sure about the risks though.
        self.linenum = linenum

        self.fmt=0b11

        line=line.replace(","," ")
        self.words=[]
        while True:
            line=line.strip()
            try:
                firstspace=line.index(" ")
                w=line[:firstspace]
                if len(w):
                    self.words.append(w)
                line=line[firstspace+1:]
            except ValueError: # no spaces left
                self.words.append(line)
                break
            
        assert self.words[0] in [ "skip", "skipto" ]

        if len(self.words) !=5:
            error("Incorrect number of operands")

        if self.words[0] == "skipto": # label
            self.dest = parse_label(self.words[1])
            self.rd = None
        else: # numeric distance
            self.dest = None
            self.rd = parse_integer_literal(self.words[1])
            if self.rd < 0:
                error(f"Distance {self.rd} must be positive, cannot skip backwards")
            if self.rd > 15:
                error(f"Distance {self.rd} is too large, cannot skip more than 15 instructions ahead")

        try:
            self.function=cond_codes[self.words[2]]
        except KeyError:
            error(f"Incorrect condition code: {self.words[2]}")
            
        self.rx = parse_gp_register_name(self.words[3])
        
        self.ry = parse_gp_register_name(self.words[4],noerror=True)
        self.immediate = 0
        self.constant=None
        if self.ry is None:
            self.immediate = 1
            # TODO: here we should check "assembler syntax conventions" as per isa card
            if self.words[4][0] == '-':
                self.sign=1
                self.constant = parse_integer_literal(self.words[4])
            else:
                self.sign=0
                self.constant = parse_integer_literal(self.words[4])

    def encode(self):
        if self.dest is not None: # resolve symbol
            try:
                dest_addr = exe.symbols[self.dest]
            except KeyError:
                error(f"Cannot resolve symbol: '{self.dest}'",self.linenum)
            self.rd = (dest_addr - self.addr)//4 - 1
            if self.rd <= 0:
                error(f"Invalid destination '{self.dest}', cannot skip backwards",self.linenum)
            if self.rd > 15:
                error(f"Destination '{self.dest}' is too far, cannot skip more than 15 instructions ahead",self.linenum)
        return super().encode()

                
class Executable():
    def __init__(self):
        self.data = {}         # maps addresses to encode()able objects
        self.symbols = {}      # maps identifiers to addresses
        self.next_addr = 0     # next free address

    def add_label(self, name):
        if name in self.symbols:
            error(f"Label '{name}' is already defined")
        self.symbols[name] = self.next_addr

    def append(self, obj):
        addr = self.next_addr
        self.data[addr] = obj
        obj.addr = addr
        self.next_addr += 4
        
    def encode(self):
        """convert `data` to a multi-line text string, 4 bytes per line"""
        if len(self.data) == 0:
            print("error: program is empty")
            sys.exit(1)
            
        if 0 not in self.data:
            error("program does not start at address zero")

        res = ""
        for addr in range(0, self.next_addr, 4):
            try:
                res += f"{self.data[addr].encode():08x}\n"
            except:
                print('ASM error while encoding instruction', self.data[addr])
                raise

        if len(self.symbols):
            res += 'SYMBOL TABLE:\n'
            for name, addr in sorted(self.symbols.items(), key=lambda pair: pair[1]):
                res += f'{addr:08x} {name}\n'
            
        return res.strip('\n')

if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument("-q","--quiet", help="Write output to files but not to the screen",action="store_true")
    argparser.add_argument("asmfilename",metavar='ASMFILE',help="path to input file")
    args=argparser.parse_args()

    if not os.path.exists(args.asmfilename):
        print(f"{argparser.prog}: cannot find file '{args.asmfilename}'")
        sys.exit(1)

    if args.asmfilename[-4:] != ".asm":
        print(f"{argparser.prog}: incorrect filename suffix '{args.asmfilename}' (expected .asm)")
        sys.exit(1)

    asmfilename=args.asmfilename
    exefile = args.asmfilename.replace('.asm','.bin')

    # remove old files to reduce confusion in case of a syntax error
    if os.path.exists(exefile): os.unlink(exefile) 

    f=open(args.asmfilename)
    asmlines=[""]+f.read().splitlines()

    exe = Executable()

    for linenum,line in enumerate(asmlines):

        # ignore comments
        if ';' in line:
            line = line[ :line.find(';') ]

        # fix whitespace and case
        line = line.strip().lower()
        line = line.replace("\t"," ")
        # strip spaces between braces -- could probably be done in one line
        m=re.search("\\[.*\\]", line) # look for [...]
        if(m): 
            repl = m.group(0).replace(" ","")
            line = re.sub("\\[.*\\]", repl, line)  
        
        # labels
        if ':' in line:
            pos    = line.find(':')
            prefix = line[:pos]
            line   = line[pos+1:]
            exe.add_label(parse_label(prefix.strip()))

        line=line.strip()
        if line == "":
            continue

        # at this point our line is label-free and comments-free
        verb = line.split()[0]
        rest = line[len(verb):].strip()
        #############################
        #### Base Instructions
        if   verb in ["halt","jump","call"]:
            exe.append(Instruction00(line))
        elif   verb == "copy":
            if 'sp' in rest:
                exe.append(Instruction10(line)) # copy to/from SP are system instructions
            else:
                exe.append(Instruction01(line)) # ordinary register copy
        elif verb in fmt_01: # ALU operations
            exe.append(Instruction01(line))
        elif verb in fmt_10: # Memory + misc.
            exe.append(Instruction10(line))
        elif verb == "let":
            rd, immed = check_generic_args(line,2)
            if rd == "sp":
                error(f"invalid use of 'let'. Use 'copy' here instead'")
            rd = 'r'+str(parse_gp_register_name(rd))

            if immed[:2]=='0x':
                if len(immed) != 10:
                    error(f"Hex constant must written as 8 digits: '{immed}'")
                    
            value = parse_integer_literal(immed,check17bits=False)

            if value > 2**31:
                value -= 2**32

            if -0xffff <= value <= 0xFFFF:
                exe.append(Instruction01(f"copy {rd} {value}"))
            elif -2**31 <= value < 2**32:
                exe.append(Instruction01(f"copy {rd} {value>>16}"))
                exe.append(Instruction01(f"lsl {rd} {rd} {16}"))
                exe.append(Instruction01(f"add {rd} {rd} {value%2**16}"))
            else:
                error(f"invalid operand '{immed}'")
        elif verb == "nop": # preferred encoding
            exe.append(Instruction01("add r0 r0 0"))
        elif verb == "not": # bitwise not
            rd, rx = check_generic_args(line, 2)
            rd=parse_gp_register_name(rd)
            rx=parse_gp_register_name(rx)
            exe.append(Instruction01(f"xor r{rd} r{rx} -1"))
        elif verb in ["skip", "skipto"]:
            exe.append(Instruction11(line))
        else:
            error(f"incorrect instruction name '{verb}'")

    # chokes on errors
    code = exe.encode()

    # if no encoding errors, only then do we create the file
    open(exefile,'w').write(code+'\n')
