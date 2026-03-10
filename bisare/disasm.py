#!/usr/bin/env python3

import argparse
import math
import os
import sys
import re

from asm import fmt_01, cond_codes

fmt_10 = {0:"store", 1:"load", 2:"push", 3:"pop",
          8:"ret",9:"swi",10:"getsr",11:"andsr",12:"orsr",13:"copy",14:"copy",15:"settlb"}
 
# invert mapping: here we need binary code to mnemonic
cond_codes_rev = { cond_codes[mnemo]:mnemo for mnemo in cond_codes }

def getbits(word, high, low=None):
    if low is None:
        low=high
    assert 31 >= high >= low >= 0

    return (word & ((1<<1+high)-1)) >> low

def signext(value, sign_bit_pos):
    assert 0 <= sign_bit_pos <= 31
    assert 0 <= value <= (1 << sign_bit_pos+1)
    if value & (1<<sign_bit_pos):
        return value - (1 << sign_bit_pos+1)
    else:
        return value

s32 = lambda x: x if x<2**31 else x-2**32 # convert to signed
u32 = lambda x: x % 2**32                 # convert to unsigned

def disassemble(addr, mem, symbols):

    IR = mem[addr]
    symbols_rev=dict() # addresses to names (computed from `symbols`)
    symbols_rev = { symbols[name]:name for name in symbols }

    fmt = getbits(IR,31,30)

    if fmt == 0b00: # JUMP or CALL
        typ=getbits(IR,29)
        offset=signext(getbits(IR,28,0), 28)
    else: # everything else
        function = getbits(IR,27,24)
        opd = getbits(IR,23,20)
        opx = getbits(IR,19,16)
        immediate = getbits(IR,28)

        s,C = getbits(IR,29), getbits(IR,15,0)
        if immediate:
            op2 = (0xFFFF0000*s) | C
            if s:
                op2=s32(op2)
        else:
            opy=getbits(IR,15,12)
            op2=0

    #if immediate: print(f'DISASM: IR={IR:08x} fmt={fmt:02b} s={s} i={immediate} function={function:04b} d={opd:04b} x={opx:04b} C=0x{C:x}')
    #else: print(f'DISASM: IR={IR:08x} fmt={fmt:02b} s={s} i=0 function={function:04b} d={opd:04b} x={opx:04b} y={opy:04x} C=0x{C:x}')
    t=""
    if fmt == 0b00:
        if addr+offset*4 in symbols_rev:
            offset=symbols_rev[addr+offset*4]
        t += f'call {offset}' if typ else f'jump {offset}'

    elif fmt == 0b10: # memory
        try:
            verb=fmt_10[function]
        except KeyError:
            return '(invalid)'
        t += f'{verb}'
        if verb == "load":
            t+=f' r{opd}'
            if not immediate:
                t+=f' [r{opx}+r{opy}]'
            elif op2==0:
                t+=f' [r{opx}]'
            elif op2>=0:
                t+=f' [r{opx}+{op2}]'
            else:
                t+=f' [r{opx}{op2}]' # minus sign is already there
        elif verb == "store":
            if not immediate:
                t+=f' [r{opx}+r{opy}]'
            elif op2==0:
                t+=f' [r{opx}]'
            elif op2>=0:
                t+=f' [r{opx}+{op2}]'
            else:
                t+=f' [r{opx}{op2}]' # minus sign is already there
            t+=f' r{opd}'
        elif verb == "push":
            t+=f' {op2}' if immediate else f' r{opy}'
        elif verb == "pop":
            t+=f' r{opd}'
        elif verb in ["ret","reti","dint","eint"]:
            pass # no operands
        elif verb == "swi":
            t+=f' {opx}'
        elif verb == "copy":
            if function == 0b1101: # save SP
                t+=f' r{opd} sp'
            else:# restore SP
                t+=f' sp {op2}' if immediate else f' sp r{opy}'
        else:
            t+=' invalid'
    elif fmt == 0b01: # alu
        try:
            t += f'{fmt_01[function]} r{opd}'
        except IndexError: # not a KeyError because fmt_01 is a list for some reason
            return '(invalid)'
        if function != 0: # COPY ignores Rx
            t+=f' r{opx}'
        t+=f' {op2}' if immediate else f' r{opy}'
    elif fmt == 0b11: # skip
        if addr+opd*4 in symbols_rev:
            t += f'skipto {symbols_rev[addr+opd*4]} '
        else:
            t += f'skip {opd} '
        try:
            t += f'{cond_codes_rev[function]} r{opx} '
        except KeyError:
            return '(invalid)'
        t += f'{op2}' if immediate else f'r{opy}'

    # remangle pseudo-instructions
    if t=='add r0 r0 0': t = 'nop'
    if t=='jump 0':      t = 'halt'

    return t




if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument("exefile",metavar='EXEFILE',help="program to execute (typically: filename.bin)")
    args=argparser.parse_args()

    if args.exefile[-4:] != ".bin":
        print(f"{argparser.prog}: incorrect filename suffix '{args.exefile}' (expected .bin)")
        sys.exit(1)

    # sanity check
    asmfile = args.exefile[:-4]+".asm"
    if os.path.exists(asmfile) and os.path.getmtime(asmfile) > os.path.getmtime(args.exefile):
        print(f"{argparser.prog}: executable is out of date !")
        print(f"please rebuild it with the following command:")
        print(f"    python3 {sys.argv[0].replace('disasm','asm')} {asmfile}")
        sys.exit(1)

    f=open(args.exefile)

    lines = f.read().splitlines()

    symbols=dict()     # names to addresses (read from the exefile)
    
    if "SYMBOL TABLE:" in lines:
        st_linenum = lines.index("SYMBOL TABLE:")
        st_lines=lines[st_linenum+1:]
        lines=lines[:st_linenum]
        
        for linenum,line in enumerate(st_lines):
            linenum+=st_linenum+1 # +1 to skip the 'boundary' line
            m=re.match("([0-9a-fA-F]{8}) +([a-zA-Z_][a-zA-Z0-9_]*)$",line)
            if m is None:
                print(f"error: incorrect line {linenum+1} in '{exefile}':")
                print(line)
                sys.exit(1)
            addr,name = int(m.group(1),16),m.group(2)
            if name in symbols:
                print(f"error: symbol {name} is already defined:")
                print(f"{exefile}:{linenum+1}: {line}")
                sys.exit(1)
            symbols[name]=addr

    mem=dict()
    addr=0
    for line in lines:
        if "SYMBOL TABLE" in line:
            break
        mem[addr]=int(line,base=16)
        addr+=4
    
    for addr in mem.keys():
        t = disassemble(addr, mem, symbols)
        
        # why the 40 columns justification ? so that we can do
        #
        #      ./asm.py prog.asm && paste <(./disasm.py prog.bin) prog.asm
        #
        for label in symbols:
            if symbols[label]==addr:
                print(f'{label}:'.ljust(40))

        print(f'{addr:04x}: {mem[addr]:08x}    {t}'.ljust(40)) 
                
