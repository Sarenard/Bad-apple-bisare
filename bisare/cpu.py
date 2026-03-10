import sys

full_hardware_ison=False # do we support mul and div instructions; off by default
exception_support_ison=False # do we support exceptions; off by default

class CPUError(Exception):
    pass

def not_yet(x,y):# because we cannot use 'raise' in a lambda
    raise NotImplementedError

from asm import fmt_01 # used for opcode-to-verb lookup

from asm import cond_codes
# invert mapping: here we need binary code to mnemonic
cond_codes = { cond_codes[mnemo]:mnemo for mnemo in cond_codes }



def smull_instr(x,y):
    if(full_hardware_ison):
        return s32( s32(x)*s32(y) )
    else:
        raise CPUError('illegal opcode')
    
def div_instr(x,y):
    if y==0: raise CPUError('division by zero')
    return s32(x) // s32(y)

def mod_instr(x,y):
    if y==0: raise CPUError('division by zero')
    return s32(x) % s32(y)


ALUOP = {
    "copy" : lambda x,y: y,
    "add"  : lambda x,y: x+y,
    "sub"  : lambda x,y: x-y,
    "or"   : lambda x,y: x|y,
    "and"  : lambda x,y: x&y,
    "xor"  : lambda x,y: x^y,
    "lsl"  : lambda x,y: x<<y if 0<=y<=32 else 0, # TODO: semantics as per ISA card
    "lsr"  : lambda x,y: x>>y if 0<=y<=32 else 0, # TODO: semantics as per ISA card
    "asr"  : lambda x,y: s32(x)>>y if 0<=y<=32 else 0, # TODO: semantics as per ISA card
    "smull": smull_instr, # TODO: semantics as per ISA card
    "smulh": not_yet, # TODO: semantics as per ISA card
    "umull": not_yet, # TODO: semantics as per ISA card
    "umulh": not_yet, # TODO: semantics as per ISA card
    "div"  : div_instr,
    "mod"  : mod_instr,
    }

COMPARE = {
    "ifeq":  lambda x,y: x==y,
    "ifne":  lambda x,y: x!=y,
    "iflt":  lambda x,y: s32(x)< s32(y),
    "ifge":  lambda x,y: s32(x)>=s32(y),
    "ifgt":  lambda x,y: s32(x)> s32(y),
    "ifle":  lambda x,y: s32(x)<=s32(y),
    "ifult": lambda x,y: u32(x)< u32(y),
    "ifuge": lambda x,y: u32(x)>=u32(y),
    "ifugt": lambda x,y: u32(x)> u32(y),
    "ifule": lambda x,y: u32(x)<=u32(y),
}

def signext(value, sign_bit_pos):
    assert 0 <= sign_bit_pos <= 31
    assert 0 <= value <= (1 << sign_bit_pos+1)
    if value & (1<<sign_bit_pos):
        return value - (1 << sign_bit_pos+1)
    else:
        return value

s32 = lambda x: x if x<(1<<31) else x-(1<<32) # convert to signed
u32 = lambda x: x % (1<<32)                 # convert to unsigned

def getbits(word, high, low=None):
    if low is None:
        low=high
    assert 31 >= high >= low >= 0

    return (word & ((1<<1+high)-1)) >> low

# interface between CPU and the outside world
bus = None

class Registers(dict):
    def __init__(self):
        for i in range(0,16):
            self[i]=0
        self.PC=0 
        self.SP=0
        self.SR=0
    def __setitem__(self, key, newvalue):
        # TODO: these are now obsolete. should remove, but add
        # equivalent checks elsewhere. and some test cases.
        if key == -1 and newvalue%4 != 0:
            raise CPUError(f'CPU error: new value for PC is not a multiple of 4: {newvalue}')
        if key == -2 and newvalue%4 != 0:
            raise CPUError(f'CPU error: new value for SP is not a multiple of 4: {newvalue}')

        super().__setitem__(key, newvalue)
        
    def pprint(self):
        """pretty-print contents of CPU registers"""
        width07 = max([len(str(s32(self[i]))) for i in range(0,8) ])
        width07 = max(width07, 3) # allow room for 'dec' header
        width07 += 1 # one space to separate columns

        width8F = max([len(str(s32(self[i]))) for i in range(8,16) ])
        width8F = max(width8F, 3) # allow room for 'dec' header
        width8F += 1 # one space to separate columns

        print(( "name"+
                "      hex "+
                "dec".rjust(width07)+
                "       "+
                "name"+
                "      hex "+
                "dec".rjust(width8F)
               ).strip())

        for i in range(0,8):
            vali=self[i]
            valj=self[i+8]
            print( f"R{i}".rjust(4)
                  +f" {vali:08x}"
                  +f" {s32(vali):{width07}d}"
                  +"       "
                  +f"R{i+8}".rjust(4)
                  +f" {valj:08x}"
                  +f" {s32(valj):{width8F}d}"
                  )
        print(  f'  PC {self.PC:08x}'
              + ' '*(10+width07)
              + f'SP {self.SP:08x}')

regs=Registers()

def step():
    """Execute a single instruction"""

    # von Neumann cycle: FETCH
    IR = bus.read(regs.PC)

    # von Neumann cycle: DECODE
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
        else:
            opy=getbits(IR,15,12)
            op2 = regs[opy]

        #if immediate: print(f'CPU DECODE: IR={IR:08x} fmt={fmt:02b} s={s} i={immediate} function={function:04b} d={opd:04b} x={opx:04b} op2=0x{op2:x}')
        #else: print(f'CPU DECODE: IR={IR:08x} fmt={fmt:02b} s={s} i=0 function={function:04b} d={opd:04b} x={opx:04b} y={opy:04x} op2=0x{op2:x}')
        
    # von Neumann cycle: EXECUTE
    if fmt == 0b00:
        if typ: # CALL
            regs.SP -= 4
            bus.write(regs.SP,regs.PC+4) # push return address
            regs.PC += offset*4
            return
        else: # JUMP
            regs.PC += offset*4
            return
    elif fmt == 0b01: # ALU ops
        try:
            regs[opd] = ALUOP[fmt_01[function]](regs[opx],op2) % (1<<32)
            regs.PC += 4
        except CPUError as e:
            # exception mechanism
            print(e)
            if exception_support_ison: # TODO no other test here?
                regs.SP -= 4
                regs.SP %= 1<<32
                bus.write(regs.SP, regs.PC+4)
                if e=="illegal opcode":
                    regs.PC = 0x00000004
                elif e=="division by 0":
                    regs.PC = 0x00000008
        return
    elif fmt == 0b10:
        if function == 0: # store
            bus.write(u32(regs[opx]+op2), regs[opd])
            regs.PC += 4
            return
        elif function == 1: #load
            regs[opd]=bus.read(u32(regs[opx]+op2))
            regs.PC += 4
            return
        elif function == 2: #push
            regs.SP -= 4 
            bus.write(regs.SP, op2)
            regs.PC += 4
            return
        elif function == 3: #pop
            regs[opd]=bus.read(regs.SP)
            regs.SP += 4 
            regs.PC += 4
            return
        elif function == 8:  #ret / reti
            regs.PC=bus.read(regs.SP)
            regs.SP += 4 # adjust SP
            if s==1: # then this ret is a reti
                raise CPUError(f'CPU error: RETI not implemented yet')
            return
        elif function == 9:  #swi
            raise CPUError(f'CPU error: SWI not implemented yet')
# From there on the ISA is still a moving target and the messages are wrong
        elif function == 10: #
            raise CPUError(f'CPU error: READSR not implemented yet')
        elif function == 12: #dint
            pass # TODO IE=0
            raise CPUError(f'CPU error: DINT not implemented yet')
        elif function == 13: #eint
            pass # TODO IE=1
            raise CPUError(f'CPU error: EINT not implemented yet')
        elif function == 13: #copy from SP
            regs[opd]=regs.SP
            regs.PC += 4 
            return
        elif function == 14: #copy to SP
            regs.SP = op2
            regs.PC += 4 # advance PC
            return
        elif function == 15: # settlb
            raise NotImplementedError
    elif fmt == 0b11: # skip
        #print(regs[opx],op2,function, cond_codes[function], COMPARE[cond_codes[function]](regs[opx],op2))
        compare = COMPARE[cond_codes[function]]
        regs.PC += 4
        if compare(regs[opx],op2):
            regs.PC += opd<<2
        return

    raise CPUError(f'CPU error: unknown instruction: 0x{IR:08x}')
