import tkinter as tk
import re
import sys
import multiprocessing as mp
import signal
import time

import cpu

# Memory mapping the keycode to address 0x0112c000

class GUI(tk.Tk):
    def __init__(self,xres,yres,data,key):
        self.xres=xres
        self.yres=yres

        self.data=data
        self.key=key

        super().__init__()
        self.title("BISARE")
        self.canvas = tk.Canvas(self,
                                background="grey50", # background color, only shows during resize
                                borderwidth=0,highlightthickness=0)
        self.img=tk.PhotoImage() # placeholder object (actual rendering happens in `update()`) 
        self.canvas.img_id=self.canvas.create_image(0,0,image=self.img,anchor=tk.NW)
        self.canvas.pack(fill=tk.BOTH,expand=1)
        
        ####################
        # zoom factor guessing: window starts centered, roughly half screen height
        sw,sh=self.winfo_screenwidth(),self.winfo_screenheight()
        zf=int(min(sw/xres/2, sh/yres/2))
        self.geometry(f'{xres*zf}x{yres*zf}+{(sw-xres*zf)//2}+{(sh-yres*zf)//2}')
        self.aspect(xres,yres,xres,yres)
        self.minsize(xres, yres)

        self.zoom_factor = zf   # current zoom factor
        self.zoom_wanted = None # new zoom factor
        self.zoom_max    = min( int((sh-50) / yres), int((sw-50) / xres))

        self.bind("<Configure>", self.on_resize)
        # 2023-09-22: we used to call `update()` from here but it felt
        # wrong. now, gui_loop() explicitely calls `after()`, so that
        # `update()` will later be called from the main event loop.
        self.bind("<KeyPress>", self.keypress_handler)
        self.bind("<KeyRelease>", self.keyrelease_handler)

    def keypress_handler(self,event):
        self.key.value=event.keycode
        # print("GUI: key pressed: ",self.key.value) # uncomment to print out keycodes

    def keyrelease_handler(self,event):
        self.key.value=0
        #print("GUI: key released")

    def on_resize(self,event):
        # Handle window resizing. Note that all actual work happens in
        # `update()` to avoid various issues (inconsistencies, seg fault)
        xratio = round(event.width/self.xres)
        yratio = round(event.height/self.yres)
        if xratio == self.zoom_factor:
            self.zoom_wanted=yratio
        elif yratio == self.zoom_factor:
            self.zoom_wanted=xratio
        else:
            self.zoom_wanted=max(xratio,yratio)
            # safety check, useful e.g. at startup when configure() is called with a 1x1 window size (!) 
        if self.zoom_wanted <1:
            self.zoom_wanted=1
        if self.zoom_wanted >self.zoom_max:
            self.zoom_wanted=self.zoom_max
        # print(f"on_resize(): {event.width}x{event.height} ~ {xratio}x{yratio} : {self.zoom_factor} -> {self.zoom_wanted}")

    # as per https://stackoverflow.com/a/63630091/117814
    # def __del__(self):
    #     print("GUI closed")
    #     for after_id in self.tk.eval('after info').split():
    #         print("canceling ",after_id)
    #         self.after_cancel(after_id)

    def update(self):
        self.after(30,self.update) # 30 ms ~ 30FPS
        try:
            super().update()
        except tk.TclError: # happens e.g. when the window is closed
            # print('TclError')
            return

        if self.zoom_wanted:
            zf=self.zoom_factor = self.zoom_wanted
            self.geometry(f'{zf*self.xres}x{zf*self.yres}')
            self.zoom_wanted = None
        try:
            ppmdata=f"P6 {self.xres} {self.yres} 255 ".encode('ascii')+self.data.raw
            self.img=tk.PhotoImage(data=ppmdata).zoom(self.zoom_factor)
            self.canvas.itemconfig(self.canvas.img_id,image=self.img)
        except tk.TclError:
            # print('TclError')
            return
        except RuntimeError:
            # when the window is closed, we get an error "Too early to create image"
            # print('RuntimeError')
            return

def on_delete_window(gui):
    # print("WM_DELETE_WINDOW")
    for after_id in gui.eval('after info').split():
        # print("after_cancel ",after_id)
        gui.after_cancel(after_id)
    gui.destroy()

def gui_loop(xres,yres,data,key):
    gui=GUI(xres,yres,data,key)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    # as per https://stackoverflow.com/a/63630091/117814
    gui.protocol('WM_DELETE_WINDOW', lambda: on_delete_window(gui))

    # GS-2023-09-22: enqueue a call to `update` so that it will be
    # picked by the actual `mainloop`.
    gui.after(0,gui.update)
    try:
        gui.mainloop()
    except Exception as e:
        # print("gui error:",e)
        raise
        
class Screen():
    def __init__(self,xres=640,yres=480):

        # pixel resolution of our video memory
        self.xres=xres
        self.yres=yres

        # three bytes per pixel mimics the tk-friendly P6 PPM format 
        self.data=mp.Array('c',xres*yres*3)

        # an attribute that holds the value of the key being presssed
        self.key=mp.Value('L') # 'L' == 32bits unsigned

        # dummy process just for is_alive()
        self.process=mp.Process()

        # show GUI on the first time simulated CPU touches us
        self.show()

    def show(self):
        if self.process.is_alive():
            return

        self.process=mp.Process(target=gui_loop, args=(self.xres,self.yres,self.data,self.key))
        self.process.daemon=True # maybe fixes the "tried to destroy photoimage" error
        self.process.start()

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
            #print('closed')
        
    def read(self,reladdr):
        if reladdr >= self.xres*self.yres*4:
            raise cpu.SimulatedError(f"VRAM read error: offset is outside range: 0x{reladdr:x}")

        if reladdr % 4:
            raise cpu.SimulatedError(f"VRAM read error: offset is not aligned: 0x{reladdr:x}")
        
        voffset = (reladdr//4)*3 # offset in video array (3 bytes per pixel)

        return (  (int.from_bytes(self.data[voffset  ],byteorder="little")<<24)
                  + (int.from_bytes(self.data[voffset+1],byteorder="little")<<16)
                  + (int.from_bytes(self.data[voffset+2],byteorder="little")<<8))
            
    def write(self,reladdr,data):
        # Note: reladdr is zero-based within the framebuffer
        if reladdr >= self.xres*self.yres*4:
            raise cpu.SimulatedError(f"VRAM write error: offset is outside range: 0x{reladdr:x}")
            
        # for now we only support single pixel writes
        if reladdr % 4:
            raise cpu.SimulatedError(f"VRAM write error: offset is not aligned: 0x{reladdr:x}")

        voffset = (reladdr//4)*3 # offset in video array (3 bytes per pixel)

        # 24-bit value to 3 bytes in big-endian order
        self.data[voffset] =   (data) & 0xFF
        self.data[voffset+1] = (data >>8) & 0xFF
        self.data[voffset+2] = (data >> 16) & 0xFF
        self.dirty = True
        # print("screen.write:", self, self.key.value)

the_screen = None

def read(reladdr):
    global the_screen
    if the_screen is None:
        the_screen=Screen()

    return the_screen.read(reladdr)

def write(reladdr,data):
    global the_screen
    if the_screen is None:
        the_screen=Screen()

    the_screen.write(reladdr,data)

def show():
    global the_screen
    if the_screen is None:
        the_screen=Screen()

    the_screen.show()

def get_key():
    global the_screen
    if the_screen is None:
        the_screen=Screen()
        
    return the_screen.key.value
