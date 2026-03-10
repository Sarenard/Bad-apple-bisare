#!/usr/bin/env python3

import argparse
import collections
import os, re, sys
import time
import random

try:
    import readline
except ImportError:
    print("warning: readline module is not installed")
    print("try this command:  python3 -m pip install pyreadline3")

import cpu
import disasm
import screen
import utils

class UserError(Exception):
    pass

def error(message):
    raise UserError(message)

def parse_unsigned_number(text):
    if re.match("0x[0-9a-fA-F]+",text): # maybe a hex address ?
        return int(text[2:], 16)
    if re.match("[1-9][0-9]*",text):    # maybe a decimal number ?
        return int(text, 10)
    if re.match("0[0-9]+",text):
        error("error: leading zeroes not allowed in decimal notation")
    if text == "0":
        return 0
    error(f"error: cannot understand number '{text}'")

def parse_number(text):
    if " " in text:
        error(f"No whitespace allowed in number: '{text}'")
    if "--" in text:
        error(f"Duplicate sign: '{text}'")
    if "+" in text:
        error(f"Plus sign not allowed here: '{text}'")
    elif len(text)>1 and text[0] == '-':
        return - parse_unsigned_number(text[1:])
    else:
        return parse_unsigned_number(text)

class Memory():
    def __init__(self,exefile):
        
        self.data    = dict() # maps multiple-of-4 addresses to 32-bit words
        self.symbols = dict() # maps names to addresses

        # load executable from file:
        f=open(exefile)

        lines = f.read().splitlines()

        st_linenum = 0 # caution: first line in file will have linenum=0
        
        if "SYMBOL TABLE:" in lines:
            st_linenum = lines.index("SYMBOL TABLE:")
            st_lines=lines[st_linenum+1:]
            lines=lines[:st_linenum]

        for linenum,line in enumerate(lines):
            if line == '':
                print(f"error: line {linenum+1} is empty")
                sys.exit(1)
                
            m=re.match("([0-9a-fA-F]{8})$",line)
            if m is None:
                print(f"error: incorrect line {linenum+1} in '{exefile}':")
                print(line)
                sys.exit(1)
            self.data[linenum*4]=int(line,base=16)

        if st_linenum: # then we have a symbol table
            for linenum,line in enumerate(st_lines):
                linenum+=st_linenum+1 # +1 to skip the 'boundary' line
                m=re.match("([0-9a-fA-F]{8}) +([a-zA-Z_][a-zA-Z0-9_]*)$",line)
                if m is None:
                    print(f"error: incorrect line {linenum+1} in '{exefile}':")
                    print(line)
                    sys.exit(1)
                addr,name = int(m.group(1),16),m.group(2)
                if name in self.symbols:
                    print(f"error: symbol {name} is already defined:")
                    print(f"{exefile}:{linenum+1}: {line}")
                    sys.exit(1)
                self.symbols[name]=addr
                
        # to get _deterministic_ random values in uninitialized reads
        # we seed the prng with the executable itself
        random.seed(str(self.data))

    def a2s(self,addr): # address to string
        """return a string representation of addr: hexadecimal digits, best-guessed length, right-justified"""
        maxlen = len("%x" % max(self.data))
        maxlen = 2*(1+(maxlen-1)//2)     # an even number of digits looks prettier
        return f"{addr:0{maxlen}x}"

    # So far, `Memory` both acts as a RAM and as a PAS dispatcher. But
    # we can separate both features one day if needed.
    def read(self, address):
        if address % 4:
            raise cpu.CPUError(f"attempt to read at a misaligned address: 0x{address:08x} is not a multiple of 4")
        if address < 0:
            raise cpu.CPUError(f"address cannot be negative: {address}")

        if 0 <= address < 0x01000000:
            if address not in self.data:
                # uninitialized memory reads as (reproducible) random values
                self.data[address]=random.randint(0,(1<<32)-1)
            return self.data[address]
        elif 0x01000000 <= address < 0x0100_0000 + 640*480*4:
            return screen.read(address-0x0100_0000)
        elif address == 0x0120_0000:
            #print("keyboard_value in sim =",screen.get_key()) 
            return screen.get_key()
        else:
            raise cpu.CPUError(f"nothing to read from at {address} /  0x{address:08x}")

    def write(self,address, newvalue):
        if address % 4:
            raise cpu.CPUError(f"attempt to write at a misaligned address: 0x{address:08x} is not a multiple of 4")
        if address < 0:
            raise cpu.CPUError(f"address cannot be negative: {address}")

        if 0 <= address < 0x01000000:
            # print(f'MEM: write at {address:08x} with value {newvalue:08x}')
            self.data[address]=newvalue
        elif 0x01000000 <= address < 0x01000000 + 640*480*4:
            screen.write(address-0x01000000, newvalue)
        else:
            raise cpu.CPUError(f"nothing to write to at {address} / 0x{address:08x}")

# speed profiling
def perf_start():
    global perf_time, perf_instr
    perf_time= time.time()
    perf_instr = 0

def perf_step():
    global perf_instr
    perf_instr += 1

def perf_stop():
    if perf_profiler_ison:
        exec_time= time.time() - perf_time
        print(f'executed {utils.eng(perf_instr)} instructions in '+utils.time2s(exec_time)
              +' i.e. '+utils.eng(perf_instr/exec_time)+' instructions per second')

# To help with formatting the help menu, we use an "ordered dict" so
# that we can maintain a distinction between a command's "real name"
# (by convention, first in the list) and and its "other names"
interactive_commands=collections.OrderedDict()

# A function decorator to help DRY when naming commands
def interactive(names):
    def decorate(cmd_func):
        assert(type(names) == list and len(names)>0)
        for name in names:
            assert name not in interactive_commands
            interactive_commands[name] = cmd_func
        return cmd_func
    return decorate

@interactive(["help","h"])
def cmd_help(words):
    """Print help screen.

    Without arguments, print the list of available commands.
    With a command name, print help text about that command.
    """
    if len(words) == 1:
        print('Available commands:')
        cmd_funcs = set( interactive_commands.values() )
        realnames = set()
        for cmd_func in cmd_funcs:
            aliases  = [ name for name,_c in interactive_commands.items()
                         if  _c == cmd_func]
            realnames.add( aliases[0] )
        maxlength = max([len(name) for name in realnames])
        for name in sorted(realnames):
            doc=interactive_commands[name].__doc__
            if doc is None:
                doc=f"No help text for '{name}'"
            print("  "+name.ljust(maxlength)+": "+doc.splitlines()[0].strip())

        print("Type 'help <cmdname>' for more details about a command")
        return

    if words[1] not in interactive_commands:
        print(f"help: unknown command: '{words[1]}'.")
        print("Type 'help' with no arguments for the help menu")
        return

    cmd_func = interactive_commands[words[1]]
    aliases  = [ name for name,_c in interactive_commands.items()
                if  _c == cmd_func ]
    if len(aliases) == 1:
        print(f"Command: '{aliases[0]}'")
    else:
        print(f"Command: '{aliases[0]}' (other names: {', '.join(aliases[1:])})")
    if cmd_func.__doc__: # reas as 'None' if cmd_func has no docstring
        print(cmd_func.__doc__.strip())
    else:
        print('no help available')

@interactive(["run","continue","cont","c"])
def cmd_run(words):
    """Unpause program execution.

    Step the CPU until either:
    - the program halts (i.e. loops on a single instruction)
    - execution causes an exception (e.g. div by zero)
    - the user presses Ctrl+C"""

    if len(words) != 1:
        raise UserError("error: this command expects no arguments")

    try:
        has_printed_control_c_message=False
        perf_start()
        while True:
            old_pc = cpu.regs.PC
            res = cpu.step()
            new_pc = cpu.regs.PC
            perf_step()
            if new_pc == old_pc:
                perf_stop()
                print(f"0x{mem.a2s(cpu.regs.PC)}: CPU halted")
                break

            if time.time()-perf_time > .5 and not has_printed_control_c_message:
                has_printed_control_c_message=True
                print("Running. Press Ctrl+C to interrupt...")
    except KeyboardInterrupt:
        perf_stop()
        if not verbose_mode_ison: # prevent info from being displayed twice
            cmd_info("")

@interactive(["step","s"])
def cmd_step(words):
    """Execute one program instruction.

    Usage: 'step' or 'step N'
    Execute just one, or N, instructions.

    Note: Press RETURN (on a blank line) after a 'step' to repeat the command.
    Note: 'step N' stops upon reaching a breakpoint.
    """
    if len(words) == 1:
        cpu.step()

    elif len(words) == 2:
        try:
            count = int(words[1])
        except ValueError:
            error(f"error: invalid decimal number '{words[1]}'")
            
        for i in range(count):
            cpu.step()
            # TODO: implement breakpoints here

@interactive(["info","i","where","w","list","l"])
def cmd_info(words):
    """Get info about system state.

    This command will print:
    - values in all CPU registers (as hexadecimal and decimal)
    - contents of memory around the address pointed to by PC
    """
    cpu.regs.pprint()
    print(f'memory view near PC:')
    start=max(0,cpu.regs.PC-8)
    cmd_memdump(['memdump', str(start),"20"])

@interactive(["memdump","md","memory","mem"])
def cmd_memdump(words):
    """Show contents of memory.

    Usage: 'memdump <location>' or 'memdump <location> <length>'
    Read <length> bytes from memory starting at <location> (label name
    or numeric address) and display their values.
    """
    if len(words) == 1:
        error("error: no target address. usage: 'memdump labelname' or 'memdump 0x1234'")

    addr = parse_unsigned_number(words[1])

    if addr %4:
        error("error: unaligned memory address: "+mem.a2s(addr))

    length=16
    if len(words)==3:
        length = parse_unsigned_number(words[2])
        if length == 0:
            error("error: size too small")

    if len(words) > 3:
        error("error: too many arguments")

    for ad in range(addr, addr+length, 4):
        w=mem.read(ad)
        # here we simulate little-endianness
        # print( f'{mem.a2s(ad)}: '
        #       +f'{w    &0xFF:02x} {w>>8&0xFF:02x} '
        #       +f'{w>>16&0xFF:02x} {w>>24    :02x}')

        for label in mem.symbols:
            if mem.symbols[label]==ad:
                print(f'  {label}:')

        pcmark = '*' if ad == cpu.regs.PC else ' '
        text = ' '*7+disasm.disassemble(ad,mem.data,mem.symbols) if ad in mem.data else ''
        print( f'{pcmark} {mem.a2s(ad)}: {w:08x}'+text)
    
@interactive(["perf"])
def cmd_perf(words):
    """Show simulator performance.

    Usage: 'perf on' or 'perf off'
    When the profiler is enabled, the simulator measures and displays execution speed.
    """
    global perf_profiler_ison
    if len(words) == 1:
        words.append("off" if perf_profiler_ison else "on")
    if words[1] == "on":
        print("performance profiler: on")
        perf_profiler_ison = True
    elif words[1] == "off":
        print("performance profiler: off")
        perf_profiler_ison = False
    else:
        raise UserError("error: usage 'perf on' or 'perf off'")

@interactive(["quit"])
def cmd_quit(words):
    """Exit the simulator.

    Stop execution and return to the shell.
    You can also press Ctrl+D."""
    sys.exit(0)

@interactive(["registers","register","reg","regs"])
def cmd_regs(words):
    """Display contents of the CPU registers."""

    if len(words) > 1: # hidden 'reg set' command
        if words[1] != "set" or len(words)!=4:
            error("usage: register set R5 42")

        reg_names = ["r0","r1","r2","r3","r4","r5","r6","r7","r8","r9",
                     "r10","r11","r12","r13","r14","r15","pc","sp"]
        if words[2] not in reg_names:
            error(f"error: incorrect register name '{words[2]}'")
        value = parse_number(words[3]) # chokes on error
        if words[2] == "pc":
            cpu.regs.PC=value
        elif words[2] == "sp":
            cpu.regs.SP=value
        else: # words[2] if of the form Rn so we just have to extract 'n'
            cpu.regs[int(words[2][1:])]=value
        
    cpu.regs.pprint()

@interactive(["screen"])
def cmd_screen(words):
    """Display the simulated screen.

    Video memory is mapped from 0x01000000 to 0x01004AFF (19200 bytes).
    The screen size (in pixels) is 640 columns by 480 lines.
    Each pixel is accessible as a 32-bit word: BBGGRR (the upper byte is ignored)
    """
    screen.show()

@interactive(["verbose","v"])
def cmd_verbose(words):
    """Always display program info.

    Usage: 'verbose on' or 'verbose off' or just 'verbose' to toggle.
    When in verbose mode, program state is displayed after each step/run.
    """
    global verbose_mode_ison
    if len(words) == 1:
        words.append("off" if verbose_mode_ison else "on")
    if words[1] == "on":
        print("verbose mode: on")
        verbose_mode_ison = True
    elif words[1] == "off":
        print("verbose mode: off")
        verbose_mode_ison = False
    else:
        raise UserError("error: usage 'verbose on' or 'verbose off'")

    
if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument("exefile",metavar='EXEFILE',help="program to execute (typically: filename.bin)")
    argparser.add_argument("-q","--quiet", help="Don't start in verbose mode",action="store_true")
    argparser.add_argument("-e","--exception_support", help="Support exceptions and interruptions",action="store_true")
    argparser.add_argument("-f","--full_hardware", help="Support the multiplication and division instructions",action="store_true")
    args=argparser.parse_args()

    if not os.path.exists(args.exefile):
        print(f"{argparser.prog}: cannot find file '{args.exefile}'")
        sys.exit(1)

    if args.exefile[-4:] != ".bin":
        print(f"{argparser.prog}: incorrect filename suffix '{args.exefile}' (expected .bin)")
        sys.exit(1)

    # sanity check
    asmfile = args.exefile[:-4]+".asm"
    if os.path.exists(asmfile) and os.path.getmtime(asmfile) > os.path.getmtime(args.exefile):
        print(f"{argparser.prog}: executable is out of date !")
        print(f"please rebuild it with the following command:")
        print(f"    python3 {sys.argv[0].replace('sim','asm')} {asmfile}")
        sys.exit(1)

    verbose_mode_ison = not args.quiet
    perf_profiler_ison = False
    perf_time=0
    perf_instr=0

    # Machine elaboration
    mem = Memory(args.exefile)
    cpu.bus=mem
    cpu.full_hardware_ison = args.full_hardware
    cpu.exception_support_ison = args.exception_support


    if verbose_mode_ison:
        cmd_info("")

    # always either: False, or a commandline to be repeated (string)
    previous_command_was_step = False

    # main interactive loop
    while True:
        try:
            cline=input('(bisare) ').strip().lower()
        except EOFError: # Ctrl+D
            print()
            cline="quit"
        except KeyboardInterrupt: # Ctrl+C
            print()
            continue
        if cline=="":
            if previous_command_was_step:
                cline= previous_command_was_step
            else:
                continue

        words = cline.split()
        if words[0] not in interactive_commands:
            print("Unknown command:",words[0])
            print("Type 'help' to know about available commands")
            continue

        cmd_func = interactive_commands[words[0]]

        try:
            cmd_func(words)
        except cpu.CPUError as e:
            print(f"0x{mem.a2s(cpu.regs.PC)}: "+str(e))
            cnd_func = None # avoid "info" screen and command auto-repetition
        except UserError as e:
            print(e)
            cmd_func = None # avoid "info" screen and command auto-repetition
            
        previous_command_was_step     = cline if (cmd_func is cmd_step)     else False
        if verbose_mode_ison and cmd_func in [ cmd_step, cmd_run ]:
            cmd_info("")
        
