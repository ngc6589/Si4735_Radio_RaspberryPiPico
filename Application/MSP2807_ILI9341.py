'''
  @ 2022 Masahiro Kusunoki masahiro.kusunoki@gmail.com
  This driver is based on lv_binding micropython generic driver named st77xx.py
  written by eudoxos and rewritten by Masahiro Kusunoki for ili9341 SKU:MSP2807.
  https://github.com/lvgl/lv_binding_micropython/blob/master/driver/generic/st77xx.py

  Initialization was based on the Adafruit.
  https://github.com/adafruit/Adafruit_ILI9341/blob/master/Adafruit_ILI9341.h
  https://github.com/adafruit/Adafruit_ILI9341/blob/master/Adafruit_ILI9341.cpp

--------------------------------------------------------------------------------
https://github.com/adafruit/Adafruit_ILI9341 readme.md
Adafruit ILI9341 Arduino Library Build StatusDocumentation

  This is a library for the Adafruit ILI9341 display products
  This library works with the Adafruit 2.8" Touch Shield V2 (SPI)

    http://www.adafruit.com/products/1651

  Adafruit 2.4" TFT LCD with Touchscreen Breakout w/MicroSD Socket - ILI9341

    https://www.adafruit.com/product/2478

  2.8" TFT LCD with Touchscreen Breakout Board w/MicroSD Socket - ILI9341

    https://www.adafruit.com/product/1770

  2.2" 18-bit color TFT LCD display with microSD card breakout - ILI9340

    https://www.adafruit.com/product/1480

  TFT FeatherWing - 2.4" 320x240 Touchscreen For All Feathers

    https://www.adafruit.com/product/3315

Check out the links above for our tutorials and wiring diagrams. These displays use SPI to communicate,
4 or 5 pins are required to interface (RST is optional).

BMP image-loading examples have been moved to the Adafruit_ImageReader library:
https://github.com/adafruit/Adafruit_ImageReader

Adafruit invests time and resources providing this open source code, please support Adafruit and
open-source hardware by purchasing products from Adafruit!

Written by Limor Fried/Ladyada for Adafruit Industries.
MIT license, all text above must be included in any redistribution

To download. click the DOWNLOADS button in the top right corner, rename the uncompressed folder Adafruit_ILI9341.
Check that the Adafruit_ILI9341 folder contains Adafruit_ILI9341.cpp and Adafruit_ILI9341.

Place the Adafruit_ILI9341 library folder your arduinosketchfolder/libraries/ folder.
You may need to create the libraries subfolder if its your first library. Restart the IDE

Also requires the Adafruit_GFX library for Arduino.
--------------------------------------------------------------------------------
MIT License

Copyright (c) [2022] [Masahiro Kusunoki]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

'''
import time
import machine
import struct
import uctypes
from micropython import const

ILI9341_SLPOUT = const(0x11)
ILI9341_GAMMASET = const(0x26)
ILI9341_DISPON = const(0x29)
ILI9341_CASET  = const(0x2A)
ILI9341_RASET  = const(0x2B)
ILI9341_RAMWR  = const(0x2C)
ILI9341_MADCTL = const(0x36)
ILI9341_VSCRSADD = const(0x37)
ILI9341_PIXFMT  = const(0x3A)
ILI9341_FRMCTR1 = const(0xB1)
ILI9341_DFUNCTR = const(0xB6)
ILI9341_PWCTR1  = const(0xC0)
ILI9341_PWCTR2  = const(0xC1)
ILI9341_VMCTR1  = const(0xC5)
ILI9341_VMCTR2  = const(0xC7)
ILI9341_GMCTRP1 = const(0xE0)
ILI9341_GMCTRN1 = const(0xE1)

MADCTL_MX = const(0x40)
MADCTL_MY = const(0x80)
MADCTL_MV = const(0x20)
MADCTL_ML = const(0x10)
MADCTL_BGR = const(0x08)
MADCTL_MH = const(0x04)

PORTRAIT = const(0)
LANDSCAPE = const(1)
INV_PORTRAIT = const(2)
INV_LANDSCAPE = const(3)

class ILIxxxx_hw(object):
    def __init__(self, *, cs = 9, dc = 8, spi, res=(240,320), bl = 13, rst = 15, rot = PORTRAIT, bgr = False, rp2_dma = None):
        '''
        This is an abstract low-level driver the ST77xx controllers, not to be instantiated directly.
        Derived classes implement chip-specific bits. THe following parameters are recognized:

        * *cs*: chip select pin (= slave select, SS)
        * *dc*: data/command pin
        * *bl*: backlight PWM pin (optional)
        * *model*: display model, to account for variations in products
        * *rst*: optional reset pin
        * *res*: resolution tuple; (width,height) with zero rotation
        * *rot*: display orientation (0: portrait, 1: landscape, 2: inverted protrait, 3: inverted landscape); the constants PORTRAIT, LANDSCAPE, INV_POTRAIT, INV_LANDSCAPE may be used.
        * *bgr*: color order if BGR (not RGB)

        Subclass constructors (implementing concrete chip) set in addition the following, not to be used directly:

        * *suppModel*: models supported by the hardware driver
        * *suppRes*: resolutions supported by the hardware driver, as list of (width,height) tuples
        '''
        self.buf1 = bytearray(1)
        self.buf2 = bytearray(2)
        self.buf4 = bytearray(4)

        self.cs = machine.Pin(cs, machine.Pin.OUT)
        self.dc = machine.Pin(dc, machine.Pin.OUT)
        self.rst = machine.Pin(rst, machine.Pin.OUT)
        self.bl = bl
        if isinstance(self.bl, int):
            self.bl = machine.PWM(machine.Pin(self.bl, machine.Pin.OUT))
        elif isinstance(self.bl,machine.Pin):
            self.bl = machine.PWM(self.bl)
        assert isinstance(self.bl,(machine.PWM, type(None)))

        self.set_backlight(10) # set some backlight
        self.rot = rot
        self.width, self.height = (0,0) # this is set later in hard_reset->config->apply_rotation
        self.res = res
        self.bgr = bgr
        self.spi = spi
        self.rp2_dma = rp2_dma
        self.hard_reset()

    def off(self):
        self.set_backlight(0)

    def hard_reset(self):
        if self.rst:
            for v in (1,0,1):
                self.rst.value(v)
                time.sleep(.2)
            time.sleep(.2)
        self.config()

    def config(self):
        self.config_hw() # defined in child classes
        self.apply_rotation(self.rot)

    def set_backlight(self,percent):
        if self.bl is None:
            return
        self.bl.duty_u16(percent*655)

    def set_window(self, x, y, w, h):
        struct.pack_into('>hh', self.buf4, 0, x, x + w - 1)
        self.write_register(ILI9341_CASET, self.buf4)
        struct.pack_into('>hh', self.buf4, 0, y, y + h - 1)
        self.write_register(ILI9341_RASET, self.buf4)

    def apply_rotation(self, rot):
        self.rot = rot
        if self.rot == 0:
            r = MADCTL_MX
            self.width  = self.res[0]
            self.height = self.res[1]
        elif self.rot == 1:
            r = MADCTL_MV
            self.width  = self.res[1]
            self.height = self.res[0]
        elif self.rot == 2:
            r = MADCTL_MY
            self.width  = self.res[0]
            self.height = self.res[1]
        elif self.rot == 3:
            r = (MADCTL_MX | MADCTL_MY | MADCTL_MV)
            self.width  = self.res[1]
            self.height = self.res[0]
        
        if self.bgr:
            self.write_register(ILI9341_MADCTL, bytes([r]))
        else:
            self.write_register(ILI9341_MADCTL, bytes([r | MADCTL_BGR]))

        
    def blit(self, x, y, w, h, buf, is_blocking=True):
        self.set_window(x, y, w, h)
        if self.rp2_dma:
            self._rp2_write_register_dma(ILI9341_RAMWR, buf, is_blocking=True)
        else:
            self.write_register(ILI9341_RAMWR, buf)

    def clear(self, color):
        bs = 128 # write pixels in chunks; makes the fill much faster
        struct.pack_into('>h', self.buf2, 0, color)
        buf = bs * bytes(self.buf2)
        npx = self.width * self.height
        self.set_window(0, 0, self.width, self.height)
        self.write_register(ILI9341_RAMWR, None)
        self.cs.value(0)
        self.dc.value(1)
        for _ in range(npx // bs):
            self.spi.write(buf)
        for _ in range(npx % bs):
            self.spi.write(self.buf2)
        self.cs.value(1)

    def write_register(self, reg, buf = None):
        struct.pack_into('B', self.buf1, 0, reg)
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(self.buf1)
        if buf is not None:
            self.dc.value(1)
            self.spi.write(buf)
        self.cs.value(1)

    def _rp2_write_register_dma(self, reg, buf, is_blocking=True):
        'If *is_blocking* is False, used should call wait_dma explicitly.'
        SPI1_BASE = 0x40040000 # FIXME: will be different for another SPI bus?
        SSPDR     = 0x008
        self.rp2_dma.config(
            src_addr  = uctypes.addressof(buf),
            dst_addr  = SPI1_BASE + SSPDR,
            count     = len(buf),
            src_inc   = True,
            dst_inc   = False,
            trig_dreq = self.rp2_dma.DREQ_SPI1_TX
        )
        struct.pack_into('B', self.buf1, 0, reg)
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(self.buf1)
        self.dc.value(1)
        self.rp2_dma.enable()

        if is_blocking:
            self.rp2_wait_dma()

    def rp2_wait_dma(self):
        '''
        Wait for rp2-port DMA transfer to finish; no-op unless self.rp2_dma is defined.
        Can be used as callback before accessing shared SPI bus e.g. with the xpt2046 driver.
        '''
        if self.rp2_dma is None: return
        while self.rp2_dma.is_busy(): pass
        self.rp2_dma.disable()
        # wait to send last byte. It should take < 1uS @ 10MHz
        time.sleep_us(10)
        self.cs.value(1)

    def _run_seq(self,seq):
        '''
        Run sequence of (initialization) commands; those are given as list of tuples, which are either
        `(command,data)` or `(command,data,delay_ms)`
        '''
        for i,cmd in enumerate(seq):
            if len(cmd)==2:
                (reg, data), delay = cmd, 0
            elif len(cmd)==3:
                reg, data, delay = cmd
            else:
                raise ValueError('Command #%d has %d items (must be 2 or 3)'%(i,len(cmd)))
            self.write_register(reg, data)
            if delay > 0:
                time.sleep_ms(delay)



class ILI9341_hw(ILIxxxx_hw):
    def __init__(self,res,**kw):
        super().__init__(res = res, **kw)

    def config_hw(self):
        init9341 = [
            (0xEF, bytes([0x03, 0x80, 0x02])),
            (0xCF, bytes([0x00, 0xC1, 0x30])),
            (0xED, bytes([0x64, 0x03, 0x12, 0x81])),
            (0xE8, bytes([0x85, 0x00, 0x78])),
            (0xCB, bytes([0x39, 0x2C, 0x00, 0x34, 0x02])),
            (0xF7, bytes([0x20])),
            (0xEA, bytes([0x00, 0x00])),
            (ILI9341_PWCTR1, bytes([0x23])),			# Power control VRH[5:0]
            (ILI9341_PWCTR2, bytes([0x10])),			# Power control SAP[2:0];BT[3:0]
            (ILI9341_VMCTR1, bytes([0x3e, 0x28])),		# VCM control
            (ILI9341_VMCTR2, bytes([0x86])),			# VCM control2
            (ILI9341_MADCTL, bytes([0x00])),
            (ILI9341_VSCRSADD, bytes([0x00])),
            (ILI9341_PIXFMT, bytes([0x55])),
            (ILI9341_FRMCTR1, bytes([0x00, 0x18])),
            (ILI9341_DFUNCTR, bytes([0x08, 0x82, 0x27])),	# Display Function Control
            (0xF2, bytes([0x00])),							# 3Gamma Function Disable
            (ILI9341_GAMMASET, bytes([0x01])),			# Gamma curve selected
            (ILI9341_GMCTRP1, bytes([0x0F, 0x31, 0x2B, 0x0C, 0x0E, 0x08, 0x4E, 0xF1, 0x37, 0x07, 0x10, 0x03, 0x0E, 0x09, 0x00])),
            (ILI9341_GMCTRN1, bytes([0x00, 0x0E, 0x14, 0x03, 0x11, 0x07, 0x31, 0xC1, 0x48, 0x08, 0x0F, 0x0C, 0x31, 0x36, 0x0F])),
            (ILI9341_SLPOUT, None, 100),
            (ILI9341_DISPON, None, 100)
            ]

        self._run_seq(init9341)


class ILIxxxx_lvgl(object):
    '''LVGL wrapper for St77xx, not to be instantiated directly.

    * creates and registers LVGL display driver;
    * allocates buffers (double-buffered by default);
    * sets the driver callback to the disp_drv_flush_cb method.

    '''
    def disp_drv_flush_cb(self, disp_drv, area, color):
#        self.rp2_wait_dma() # wait if not yet done and DMA is being used
        self.rp2_wait_dma()
        self.blit(area.x1,
                  area.y1,
                  w := (area.x2 - area.x1 + 1),
                  h := (area.y2 - area.y1 + 1),
                  color.__dereference__(2 * w * h),
                  is_blocking=False
                  )
        self.disp_drv.flush_ready()

    def __init__(self, doublebuffer = True, factor = 4):
        import lvgl as lv
        import lv_utils
        if lv.COLOR_DEPTH != 16:
            raise RuntimeError(f'LVGL *must* be compiled with LV_COLOR_DEPTH=16')
        
        bufSize = (self.width * self.height * lv.color_t.__SIZE__) // factor

        if not lv.is_initialized():
            lv.init()
        # create event loop if not yet present
        if not lv_utils.event_loop.is_running():
            self.event_loop = lv_utils.event_loop()

        # attach all to self to avoid objects' refcount dropping to zero when the scope is exited
        self.disp_drv = lv.disp_create(self.width, self.height)
        self.disp_drv.set_flush_cb(self.disp_drv_flush_cb)
        self.disp_drv.set_draw_buffers(bytearray(bufSize), bytearray(bufSize) if doublebuffer else None, bufSize, lv.DISP_RENDER_MODE.PARTIAL)
        self.disp_drv.set_color_format(lv.COLOR_FORMAT.NATIVE if self.bgr else lv.COLOR_FORMAT.NATIVE_REVERSED)


class ILI9341(ILI9341_hw, ILIxxxx_lvgl):
    def __init__(self, res, doublebuffer = True, factor = 4, **kw):
        ILI9341_hw.__init__(self, res = res, **kw)
        ILIxxxx_lvgl.__init__(self, doublebuffer, factor)
