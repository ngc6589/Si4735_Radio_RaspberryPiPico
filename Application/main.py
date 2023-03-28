import machine
import rp2_dma
import sys
import time
import json
import lvgl as lv
import MSP2807_ILI9341
import MSP2807_XPT2046

mutesp = machine.Pin(26, machine.Pin.OUT)
mutehp = machine.Pin(27, machine.Pin.OUT)
mutesp.value(1)
mutehp.value(1)

def printBytes(bs):
    for i in range(len(bs)):
        printHex(bs[i])
    print()

def printHex(h):
    tbl = "0123456789ABCDEF"
    r = h % 16
    x = int(h / 16)
    print(tbl[x], end="")
    print(tbl[r], end="")
    print(" ", end="")

# Generate 48k I2S clock
# uncomment I2S OUTPUT
# @rp2.asm_pio(
#     sideset_init=(rp2.PIO.OUT_HIGH, rp2.PIO.OUT_HIGH)
# )
# def gen48k():
#     set(x, 30)       .side(0b00) [1]
#     nop()            .side(0b01) [1]
#     label("L01")
#     nop()            .side(0b00) [1]
#     jmp(x_dec, "L01").side(0b01) [1]
#     set(x, 30)       .side(0b10) [1]
#     nop()            .side(0b11) [1]
#     label("R01")
#     nop()            .side(0b10) [1]
#     jmp(x_dec, "R01").side(0b11) [1]
# 
# sm0 = rp2.StateMachine(
#     0,
#     gen48k,
#     freq=12_288_000,
#     sideset_base=machine.Pin(4)
# )
# sm0.active(1)

@rp2.asm_pio(
    set_init=(rp2.PIO.OUT_HIGH)
)
def gen32k():
    set(pins, 1) [4]
    set(pins, 0) [4]

sm1 = rp2.StateMachine(
    1,
    gen32k,
    freq=327_680,
    set_base=machine.Pin(6)
)
sm1.active(1)

class Si4735(object):
    mode = [
        ['FM',  76000,108000, 10],
        ['AM',    531,  1602,  9],
        ['LW',    153,   279,  9],
        ['120m', 2300,  2495,  5],
        ['90m',  3200,  3400,  5],
        ['75m',  3900,  4000,  5],
        ['60m',  4750,  5060,  5],
        ['49m',  5730,  6295,  5],
        ['41m',  7100,  7600,  5],
        ['31m',  9250,  9900,  5],
        ['25m', 11600, 12100,  5],
        ['22m', 13570, 13870,  5],
        ['19m', 15030, 15800,  5],
        ['16m', 17480, 17900,  5],
        ['15m', 18900, 19020,  5],
        ['13m', 21450, 21750,  5],
        ['11m', 25670, 26100,  5],
        ['SW',   2300, 26100,  5]
    ]

    def __init__(self, i2c, reset = 22):
        self.addr=0x63
        self.i2c=i2c
        self.reset = machine.Pin(reset, machine.Pin.OUT)
        self.hard_reset()
        self.modeIdx = -1

    def getModeIdx(self, khz):
        for i in range(len(self.mode)):
            if khz >= self.mode[i][1] and khz <= self.mode[i][2]:
                return i
        return -1

    def hard_reset(self):
        if self.reset:
            for val in (1, 0, 1):
                self.reset.value(val)
                time.sleep(0.1)
            time.sleep(0.1)

    def setProperty(self, buf=None):
        self.buf = bytes([0x12, 0x00]) + buf
        self.i2c.writeto(self.addr, self.buf)
        self.waitCTS()
        
    def getProperty(self, buf=None):
        self.i2c.writeto(self.addr, bytes([0x13, 0x00]) + buf)
        self.waitCTS()
        self.resp = self.i2c.readfrom(self.addr, 4)
        print("getProperty: ",end="")
        printBytes(self.resp)

    def FMPOWER_UP(self):
        self.i2c.writeto(self.addr, bytes([0x01, 0x00, 0x05]))  # analog Out
#         self.i2c.writeto(self.addr, bytes([0x01, 0x00, 0xB0]))   # I2S
        self.waitCTS()
        time.sleep(0.5)
        self.setProperty(bytes([0xFF, 0x00, 0x00, 0x00]))          # Turn off Debug Mode
#         self.setProperty(bytes([0x01, 0x04, 0xBB, 0x80]))        # I2s sample rate

    def FM_SEEK_BAND_BOTTOM(self, freq):
        self.setProperty(bytes([0x14, 0x00]) + freq.to_bytes(2, 'big'))

    def FM_SEEK_BAND_TOP(self, freq):
        self.setProperty(bytes([0x14, 0x01]) + freq.to_bytes(2, 'big'))

    def FM_SEEK_FREQ_SPACING(self, step):
        self.setProperty(bytes([0x14, 0x02, 0x00]) + step.to_bytes(1, 'big')) # 5(50kHz), 10(100kHz), 20(200kHz)

    def AMPOWER_UP(self):
        self.i2c.writeto(self.addr, bytes([0x01, 0x01, 0x05])) # analog out
#         self.i2c.writeto(self.addr, bytes([0x01, 0x01, 0xB0]))  # I2S
        self.waitCTS()
        time.sleep(0.5)
        self.setProperty(bytes([0xFF, 0x00, 0x00, 0x00]))         # Turn off Debug Mode
#         self.setProperty(bytes([0x01, 0x04, 0xBB, 0x80]))       # I2S sample rate

    def AM_SEEK_BAND_BOTTOM(self, freq):
        self.setProperty(bytes([0x34, 0x00]) + freq.to_bytes(2, 'big'))

    def AM_SEEK_BAND_TOP(self, freq):
        self.setProperty(bytes([0x34, 0x01]) + freq.to_bytes(2, 'big'))

    def AM_SEEK_FREQ_SPACING(self, step):
        self.setProperty(bytes([0x34, 0x02, 0x00]) + step.to_bytes(1, 'big')) # 1 (1kHz), 5 (5kHz), 9 (9kHz), and 10 (10kHz).

    def POWER_DOWN(self):
        self.i2c.writeto(self.addr, bytes([0x11]))
        self.waitCTS()
        time.sleep(1)
    
    def setFMDeEmphasis(self):
        self.setProperty(bytes([0x11, 0x00, 0x00, 0x01]))  # 01 = 50 μs. Used in Europe, Australia, Japan

    def FM_TUNE_FREQ(self, freq, fast=None):
        self.freq=freq
        self.fast=fast
        param = bytes([0x20, 0x00]) if fast == None else bytes([0x20, 0x01])
        self.i2c.writeto(self.addr, param + freq.to_bytes(2, 'big'))
        self.waitCTS()

    def AM_TUNE_FREQ(self, freq, fast=None):
        self.freq=freq
        self.fast=fast
        param = bytes([0x40, 0x00]) if fast == None else bytes([0x40, 0x01])
        self.i2c.writeto(self.addr, param + freq.to_bytes(2, 'big'))
        self.waitCTS()

    def FM_SEEK_START(self, seekDir):
        arg1 = 0b00001100 if seekDir == 1 else 0b00000100
        self.i2c.writeto(self.addr, bytes([0x21, arg1]))
        self.waitCTS()

    def AM_SEEK_START(self, seekDir):
        arg1 = 0b00001100 if seekDir == 1 else 0b00000100
        self.i2c.writeto(self.addr, bytes([0x41, arg1]))
        self.waitCTS()

    def FM_TUNE_STATUS(self):
        self.i2c.writeto(self.addr, bytes([0x22, 0x00]))
        self.waitCTS()
        resp = self.i2c.readfrom(self.addr, 7)
        self.freq = resp[2] * 256
        self.freq = self.freq + resp[3]
        self.rssi = resp[4]
        self.snr  = resp[5]
        self.valid = resp[1] & 0b0000_0001

    def AM_TUNE_STATUS(self):
        self.i2c.writeto(self.addr, bytes([0x42, 0x00]))
        self.waitCTS()
        resp = self.i2c.readfrom(self.addr, 7)
        self.freq = resp[2] * 256
        self.freq = self.freq + resp[3]
        self.rssi = resp[4]
        self.snr  = resp[5]
        self.valid = resp[1] & 0b0000_0001

    def FM_RSQ_STATUS(self):
        self.i2c.writeto(self.addr, bytes([0x23, 0x00]))
        self.waitCTS()
        resp = self.i2c.readfrom(self.addr, 7)
        self.rssi = resp[4]
        self.snr  = resp[5]
        self.stblend = resp[3] & 0x7f
        self.valid = resp[2] & 0b0000_0001

    def AM_RSQ_STATUS(self):
        self.i2c.writeto(self.addr, bytes([0x43, 0x00]))
        self.waitCTS()
        resp = self.i2c.readfrom(self.addr, 7)
        self.rssi = resp[4]
        self.snr  = resp[5]
        self.stblend = resp[3] & 0x7f
        self.valid = resp[2] & 0b0000_0001

    def setVolume(self, vol):
        self.vol = vol
        if self.vol > 63:
            self.vol = 63
        self.setProperty(bytes([0x40, 0x00]) + self.vol.to_bytes(2, 'big'))

    def unmute(self):
        self.setProperty(bytes([0x40, 0x01, 0x00, 0x00]))

    def mute(self):
        self.setProperty(bytes([0x40, 0x01, 0x00, 0x03]))

    def waitCTS(self):
        while True:
            cts = self.i2c.readfrom(self.addr, 1)
            if cts >= b'0x80': break

    def getFmFreqStr(self):
        f1 = str(self.freq / 100)
        f1last = len(f1)
        if f1last > 6:
            f2 = f1[f1last - 1]
            f3 = f1.rstrip(f2)
            f4 = f3.rstrip('0')
        else:
            f4 = f1.rstrip('0')
        if f4[-1] == '.': f4 = f4 + "0"
        f4 = f4 + "MHz"
        return f4

    def getAmFreqStr(self):
        f1 = str(self.freq)
        f1 = f1 + "kHz"
        return f1

i2c = machine.I2C(0, scl=machine.Pin(21), sda=machine.Pin(20), freq=50_000)
spi=machine.SPI(
    1,
    baudrate=43_000_000,
    polarity=0,
    phase=0,
    sck=machine.Pin(10,machine.Pin.OUT),
    mosi=machine.Pin(11,machine.Pin.OUT),
    miso=machine.Pin(12,machine.Pin.IN)
)        

dma0=rp2_dma.DMA(1)

disp = MSP2807_ILI9341.ILI9341(
    rot=MSP2807_ILI9341.PORTRAIT,
    res=(240,320),
    spi=spi,
    cs=9,
    dc=8,
    bl=13,
    rst=15,
    doublebuffer=True,
    factor = 8,
    bgr=False,
    rp2_dma=dma0
)
disp.set_backlight(100)

spi2 = machine.SoftSPI(
    baudrate=1_000_000,
    polarity=0,
    phase=0,
    sck =machine.Pin(17,machine.Pin.OUT),
    mosi=machine.Pin(18,machine.Pin.OUT),
    miso=machine.Pin(19,machine.Pin.IN)
)
touch = MSP2807_XPT2046.Xpt2046(spi=spi2,cs=16,rot=MSP2807_XPT2046.PORTRAIT)

tabview = lv.tabview(lv.scr_act(), lv.DIR.BOTTOM, 16)
tab1 = tabview.add_tab("MAIN")
tab2 = tabview.add_tab("Station")

def tab1_event(e):
    if btnStepDown.is_visible():
        btnStepDown.add_flag(lv.obj.FLAG.HIDDEN)
        btnStepUp.add_flag(lv.obj.FLAG.HIDDEN)
        kbd.clear_flag(lv.obj.FLAG.HIDDEN)
        st.contVisible(False)
    else:
        btnStepDown.clear_flag(lv.obj.FLAG.HIDDEN)
        btnStepUp.clear_flag(lv.obj.FLAG.HIDDEN)
        kbd.add_flag(lv.obj.FLAG.HIDDEN)
        st.contVisible(True)

tab1.add_event(tab1_event, lv.EVENT.LONG_PRESSED, None)

class freqStep(object):
    def __init__(self):
        self.col_dsc = [40, 40, 40, 40, lv.GRID_TEMPLATE_LAST]
        self.row_dsc = [18, 18, lv.GRID_TEMPLATE_LAST]
        self.step = [
            [1,"1k"], [5,"5k"], [9,"9k"], [10,"10k"],
            [50,"50k"], [100,"100k"], [500,"500k"], [1000,"1M"],
        ]
        self.stepIdx = 0
        self.lastFmIdx = 5
        self.lastAmIdx = 1
        self.createTable()

    def step_cb(self, event_struct):
        event = event_struct.code
        if event == lv.EVENT.CLICKED:
            if self.mode == 0:
                self.lastfmidx = self.stepIdx
            else:
                self.lastamidx = self.stepIdx
            targetLabel = event_struct.get_target_obj()
            self.stepIdx = targetLabel.get_index()
            self.changebg(self.stepIdx)

    def createTable(self):
        self.cont = lv.obj(tab1)
        self.cont.set_style_grid_column_dsc_array(self.col_dsc, 0)
        self.cont.set_style_grid_row_dsc_array(self.row_dsc, 0)
        self.cont.set_size(lv.pct(100), lv.pct(27))
        self.cont.set_style_bg_color( lv.color_hex(0xe0e0ff), lv.PART.MAIN | lv.STATE.DEFAULT )
        self.cont.align_to(tab1, lv.ALIGN.BOTTOM_MID, 0, -42)
        self.cont.set_layout(lv.LAYOUT_GRID.value)

        for i in range(len(self.step)):
            col = i % 4
            row = i // 4
            obj = lv.label(self.cont)
            obj.set_style_bg_color( lv.color_hex(0xffffff), lv.PART.MAIN | lv.STATE.DEFAULT )
            obj.set_style_bg_opa(255, lv.PART.MAIN| lv.STATE.DEFAULT )
            obj.set_style_text_font(lv.font_montserrat_12, 0)
            obj.set_style_text_align( lv.TEXT_ALIGN.CENTER, lv.PART.MAIN | lv.STATE.DEFAULT )
            obj.set_style_border_color( lv.color_hex(0xFF0000), lv.PART.MAIN | lv.STATE.DEFAULT )
            obj.set_style_border_width( 1, lv.PART.MAIN | lv.STATE.DEFAULT )
            obj.set_style_pad_left( 1, lv.PART.MAIN | lv.STATE.DEFAULT )
            obj.set_style_pad_right( 1, lv.PART.MAIN | lv.STATE.DEFAULT )
            obj.set_style_pad_top( 1, lv.PART.MAIN | lv.STATE.DEFAULT )
            obj.set_style_pad_bottom( 1, lv.PART.MAIN | lv.STATE.DEFAULT )
            obj.set_style_radius( 8, lv.PART.MAIN | lv.STATE.DEFAULT )
            obj.add_event(self.step_cb, lv.EVENT.ALL, None)
            obj.set_text(self.step[i][1])
            obj.set_grid_cell(lv.GRID_ALIGN.STRETCH, col, 1,
                              lv.GRID_ALIGN.STRETCH, row, 1)

    def getStep(self):
        if self.mode == 0:
            return int(self.step[self.stepIdx][0] / 10)
        elif self.mode == 1:
            return self.step[self.stepIdx][0]
        else:
            return 0

    def changebg(self, idx):
        if self.mode == 0:
            for i in (0,1,2,3):
                obj = self.cont.get_child(i)
                obj.set_style_bg_color( lv.color_hex(0xA0A0A0), lv.PART.MAIN | lv.STATE.DEFAULT )
            for i in (4,5,6,7):
                obj = self.cont.get_child(i)
                obj.set_style_bg_color( lv.color_hex(0xffffff), lv.PART.MAIN | lv.STATE.DEFAULT )
        elif self.mode == 1:
            for i in range(8):
                obj = self.cont.get_child(i)
                obj.set_style_bg_color( lv.color_hex(0xffffff), lv.PART.MAIN | lv.STATE.DEFAULT )
        obj = self.cont.get_child(idx)
        obj.set_style_bg_color( lv.color_hex(0xff8080), lv.PART.MAIN | lv.STATE.DEFAULT )
        self.stepIdx = idx
        if self.mode == 0:
            self.lastFmIdx = self.stepIdx
        elif self.mode == 1:
            self.lastAmIdx = self.stepIdx

    def changeFM(self):
        self.mode = 0
        for i in range(4):
            obj = self.cont.get_child(i)
            obj.clear_flag(lv.obj.FLAG.CLICKABLE)
        self.changebg(self.lastFmIdx)

    def changeAM(self):
        self.mode = 1
        for i in range(8):
            obj = self.cont.get_child(i)
            obj.add_flag(lv.obj.FLAG.CLICKABLE)
        self.changebg(self.lastAmIdx)

    def contVisible(self, visi=True):
        if visi == True:
            self.cont.clear_flag(lv.obj.FLAG.HIDDEN)
        else:
            self.cont.add_flag(lv.obj.FLAG.HIDDEN)


labelTitle = lv.label(tab1)
labelTitle.set_width(lv.pct(50))
labelTitle.set_text("Si4735 RADIO\nJP3SRS")
labelTitle.set_style_text_font(lv.font_GenJyuuGothic_Normal_16, 0)
labelTitle.set_style_text_align( lv.TEXT_ALIGN.RIGHT, lv.PART.MAIN | lv.STATE.DEFAULT )
#labelTitle.set_long_mode(lv.label.LONG.SCROLL_CIRCULAR)
labelTitle.align(lv.ALIGN.TOP_RIGHT, 0, 0)

kbd_map = ["7", "8", "9", "M", "\n",
          "4", "5", "6", "k", "\n",
          "1", "2", "3", "C", "\n",
          "0", ".", "<<" ,">>", None]

kbd_ctrl = [ 2, 2, 2, 2,
            2, 2, 2, 2,
            2, 2, 2, 2,
            2, 2, 2, 2 ]

saveFreq = ""
def kbd_valueChange(event_struct):
    btnm = lv.btnmatrix.__cast__(event_struct.get_target())
    btn = btnm.get_selected_btn()
    txt = btnm.get_btn_text(btn)
    global saveFreq
    if txt == "<<":
        kbdTextArea.del_char()
        kbdTextArea.del_char()
        if len(saveFreq) > 0: return
        if radio.modeIdx == 0:
            radio.FM_SEEK_START(0)
        elif radio.modeIdx > 0:
            radio.AM_SEEK_START(0)
        timer1.resume()
        return
    if txt == ">>":
        kbdTextArea.del_char()
        kbdTextArea.del_char()
        if len(saveFreq) > 0: return
        if radio.modeIdx == 0:
            radio.FM_SEEK_START(1)
        elif radio.modeIdx >0:
            radio.AM_SEEK_START(1)
        timer1.resume()
        return
    if txt == "C":
        a = kbdTextArea.get_text()
        if len(a) > 2 and a[-1] == 'C' and a[-2] == 'z':
            kbdTextArea.del_char()
            saveFreq = kbdTextArea.get_text()
            kbdTextArea.set_text("")
            timer1.pause()
        elif len(saveFreq) > 0:
            kbdTextArea.set_text(saveFreq)
            saveFreq = ""
            timer1.resume()
        return
    taText = kbdTextArea.get_text()
    if len(taText) > 3:
        if taText[-2] == "z":
            kbdTextArea.del_char()
            return
    if txt == ".":
        taText = kbdTextArea.get_text()
        dot = 0
        for i in taText:
            if i == ".":
                dot += 1
        if dot > 1:
            kbdTextArea.del_char()
            return
    if txt == "M" or txt == "k":
        saveFreq = ""
        kbdTextArea.add_text("Hz")
        radioTune(kbdTextArea.get_text())
        timer1.resume()

def btnStepDown_cb(event):
    timer1.pause()
    newFreq = radio.freq - st.getStep()
    if radio.modeIdx == 0:
        if (newFreq * 10) >= radio.mode[0][1] and (newFreq * 10) <= radio.mode[0][2]:
            radio.FM_TUNE_FREQ(newFreq, fast = True)
            kbdTextArea.set_text(radio.getFmFreqStr())
    else:
        if newFreq >= 149 and newFreq <= 23000:
            newMode = radio.getModeIdx(newFreq)
            if newMode != radio.modeIdx:
                modeBtnLabel.set_text(radio.mode[newMode][0])
                radio.modeIdx = newMode
            radio.AM_TUNE_FREQ(newFreq, fast = True)
            kbdTextArea.set_text(radio.getAmFreqStr())
    timer1.resume()

def btnStepUp_cb(event):
    timer1.pause()
    newFreq = radio.freq + st.getStep()
    if radio.modeIdx == 0:
        if newFreq * 10 >= radio.mode[0][1] and newFreq * 10 <= radio.mode[0][2]:
            radio.FM_TUNE_FREQ(newFreq, fast = True)
            kbdTextArea.set_text(radio.getFmFreqStr())
    else:
        if newFreq >= 149 and newFreq <= 23000:
            newMode = radio.getModeIdx(newFreq)
            if newMode != radio.modeIdx:
                modeBtnLabel.set_text(radio.mode[newMode][0])
                radio.modeIdx = newMode
            radio.AM_TUNE_FREQ(newFreq, fast = True)
            kbdTextArea.set_text(radio.getAmFreqStr())
    timer1.resume()

btnStepDown = lv.btn(tab1)
btnStepDown.add_event(btnStepDown_cb, lv.EVENT.CLICKED, None)
btnStepDown.add_event(btnStepDown_cb, lv.EVENT.LONG_PRESSED_REPEAT, None)
btnStepDown.set_width(lv.pct(40))
btnStepDown.align_to(tab1, lv.ALIGN.BOTTOM_MID, -50, -18)
btnStepDownLabel = lv.label(btnStepDown)
btnStepDownLabel.set_text("<<")
btnStepDownLabel.align_to(btnStepDown, lv.TEXT_ALIGN.CENTER, 0,0)

btnStepUp = lv.btn(tab1)
btnStepUp.add_event(btnStepUp_cb, lv.EVENT.CLICKED, None)
btnStepUp.add_event(btnStepUp_cb, lv.EVENT.LONG_PRESSED_REPEAT, None)
btnStepUp.set_width(lv.pct(40))
btnStepUp.align_to(tab1, lv.ALIGN.BOTTOM_MID, 50, -18)
btnStepUpLabel = lv.label(btnStepUp)
btnStepUpLabel.set_text(">>")
btnStepUpLabel.align_to(btnStepUp, lv.TEXT_ALIGN.CENTER, 0,0)

kbd = lv.keyboard(tab1)
kbd.set_y(0)
kbd.set_map(lv.keyboard.MODE.USER_1, kbd_map, kbd_ctrl)
kbd.set_mode(lv.keyboard.MODE.USER_1)
kbd.add_event(kbd_valueChange, lv.EVENT.VALUE_CHANGED, None)
kbd.set_width(lv.pct(100))
kbd.set_height(lv.pct(42))
kbd.align_to(tab1, lv.ALIGN.BOTTOM_MID, 0, 0)
kbd.add_flag(lv.obj.FLAG.HIDDEN)

kbdTextArea = lv.textarea(tab1)
kbdTextArea.set_style_text_font(lv.font_GenJyuuGothic_Monospace_Medium_34, 0)
kbdTextArea.set_width(lv.pct(100))
kbdTextArea.set_height(lv.pct(18))
kbdTextArea.align_to(kbd, lv.ALIGN.TOP_MID, 0, -80)
kbdTextArea.add_state(lv.STATE.FOCUSED)
kbdTextArea.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
kbdTextArea.clear_flag(lv.obj.FLAG.CLICKABLE)
kbdTextArea.clear_flag(lv.obj.FLAG.SCROLLABLE)
kbdTextArea.set_style_text_align( lv.TEXT_ALIGN.CENTER, lv.PART.MAIN | lv.STATE.DEFAULT)
kbdTextArea.clear_state(lv.STATE.FOCUSED)
kbdTextArea.set_one_line(True)
kbd.set_textarea(kbdTextArea)

def volumeSlider_event_cb(event):
    slider = event.get_target_obj()
    volumeSliderLabel.set_text("Vol {:d}".format(slider.get_value()))
    volumeSliderLabel.align_to(slider, lv.ALIGN.LEFT_MID, -60, 0)
    radio.setVolume(slider.get_value())

volumeSlider = lv.slider(tab1)
volumeSlider.set_width(lv.pct(60))
volumeSlider.set_height(lv.pct(5))
volumeSlider.align_to(kbdTextArea, lv.ALIGN.TOP_RIGHT, 0, -30)
volumeSlider.set_range(0,63)
volumeSlider.add_event(volumeSlider_event_cb, lv.EVENT.VALUE_CHANGED, None)

volumeSliderLabel = lv.label(tab1)
volumeSliderLabel.set_text("Vol 0")
volumeSliderLabel.align_to(volumeSlider, lv.ALIGN.LEFT_MID, -60, 0)

style_indic = lv.style_t()
style_indic.init()
style_indic.set_bg_opa(lv.OPA.COVER)
style_indic.set_bg_color(lv.color_hex(0x800000))
style_indic.set_bg_grad_color(lv.color_hex(0xff0000))
style_indic.set_bg_grad_dir(lv.GRAD_DIR.HOR)
smeterBar = lv.bar(tab1)
smeterBar.add_style(style_indic, lv.PART.INDICATOR)
smeterBar.set_size(100, 10)
smeterBar.set_range(0, 160)
smeterBar.align_to(kbdTextArea, lv.ALIGN.BOTTOM_MID, 50, 25)
smeterBar.set_value(0, lv.ANIM.OFF)

labelSignal = lv.label(tab1)
labelSignal.set_text("000dBu")
labelSignal.set_style_text_font(lv.font_montserrat_12, 0)
labelSignal.align_to(smeterBar, lv.ALIGN.LEFT_MID, -54, 0)

labelSnr = lv.label(tab1)
labelSnr.set_text("000dB")
labelSnr.set_style_text_font(lv.font_montserrat_12, 0)
labelSnr.align_to(labelSignal, lv.ALIGN.LEFT_MID, -40, 0)

modeBtnLabel = lv.label(tab1)
modeBtnLabel.set_text("")
modeBtnLabel.set_style_text_font(lv.font_GenJyuuGothic_Monospace_Medium_34, 0)
modeBtnLabel.set_style_text_color( lv.color_hex(0xffffff), lv.PART.MAIN | lv.STATE.DEFAULT )
modeBtnLabel.set_style_text_opa(255, lv.PART.MAIN| lv.STATE.DEFAULT )
modeBtnLabel.set_style_text_align( lv.TEXT_ALIGN.CENTER, lv.PART.MAIN | lv.STATE.DEFAULT )
modeBtnLabel.set_width(lv.pct(40))	# 1
modeBtnLabel.set_height(36)   # 1
modeBtnLabel.set_align(lv.ALIGN.TOP_LEFT)
modeBtnLabel.set_style_pad_left( 2, lv.PART.MAIN | lv.STATE.DEFAULT )
modeBtnLabel.set_style_pad_right( 2, lv.PART.MAIN | lv.STATE.DEFAULT )
modeBtnLabel.set_style_pad_top( 2, lv.PART.MAIN | lv.STATE.DEFAULT )
modeBtnLabel.set_style_pad_bottom( 2, lv.PART.MAIN | lv.STATE.DEFAULT )
modeBtnLabel.set_style_bg_color(lv.color_hex(0xa0a0a0), lv.PART.MAIN | lv.STATE.DEFAULT)
modeBtnLabel.set_style_bg_opa(255, lv.PART.MAIN | lv.STATE.DEFAULT)
modeBtnLabel.set_style_radius( 8, lv.PART.MAIN | lv.STATE.DEFAULT )

labelSTBLEND = lv.label(tab1)
labelSTBLEND.set_text("000%")
labelSTBLEND.set_style_text_font(lv.font_montserrat_12, 0)
labelSTBLEND.set_style_bg_color(lv.color_make(255, 255, 255), lv.PART.MAIN | lv.STATE.DEFAULT)
labelSTBLEND.set_style_bg_opa(255, lv.PART.MAIN | lv.STATE.DEFAULT)
labelSTBLEND.set_style_pad_left( 2, lv.PART.MAIN | lv.STATE.DEFAULT )
labelSTBLEND.set_style_pad_right( 2, lv.PART.MAIN | lv.STATE.DEFAULT )
labelSTBLEND.set_style_pad_top( 2, lv.PART.MAIN | lv.STATE.DEFAULT )
labelSTBLEND.set_style_pad_bottom( 2, lv.PART.MAIN | lv.STATE.DEFAULT )
labelSTBLEND.align_to(modeBtnLabel, lv.ALIGN.BOTTOM_LEFT, 0, 24)

# -- tab2 screen --
class stationList(object):
    def __init__(self):
        self.table = lv.table(tab2)
        self.table.align(lv.ALIGN.TOP_MID, 0, 36)
        self.table.set_col_width(0, 130)
        self.table.set_col_width(1, 80)
        self.table.set_height(240)
        self.table.set_style_text_font(lv.font_GenJyuuGothic_Normal_16, 0)
        self.table.set_style_pad_left(4, lv.PART.ITEMS | lv.STATE.DEFAULT)
        self.table.set_style_pad_right(4, lv.PART.ITEMS | lv.STATE.DEFAULT)
        self.table.set_style_pad_top(4, lv.PART.ITEMS|lv.STATE.DEFAULT)
        self.table.set_style_pad_bottom(4, lv.PART.ITEMS | lv.STATE.DEFAULT)

    def table_event_cb(self,event):
        code = event.get_code()
        obj = event.get_target_obj()
        row = lv.C_Pointer()
        col = lv.C_Pointer()
        obj.get_selected_cell(row, col)
        fstr = obj.get_cell_value(row.uint_val, 1)
        radioTune(fstr)

    def dispStationat(self, area):
        self.fname = area + ".txt"
        with open(self.fname, "r") as f:
            self.lines = f.read().splitlines()
        self.table.clean()
        self.table.set_row_cnt(0)
        for i in range(len(self.lines)):
            self.table.set_cell_value(int(i/2), 0, self.lines[i]) if i % 2 == 0 else self.table.set_cell_value(int(i/2), 1, self.lines[i])
        self.table.add_event(self.table_event_cb, lv.EVENT.VALUE_CHANGED, None)

stations = stationList()
st = freqStep()
st.changeAM()
st.changebg(1)

def areabtn_cb(event):
    code = event.get_code()
    obj = event.get_target_obj()
    label= obj.get_child(0)
    #print("press: " + label.get_text())
    stations.dispStationat(label.get_text())

for i in range(10):
    areabtn = lv.btn(tab2)
    areabtn.set_width(16)
    areabtn.set_height(20)
    areabtn.add_event(areabtn_cb, lv.EVENT.CLICKED, None)
    areabtn.align(lv.ALIGN.TOP_LEFT, 6 + i * 20, 2)
    aliabtnlabel = lv.label(areabtn)
    aliabtnlabel.set_text(str(i))
    aliabtnlabel.align_to(areabtn, lv.ALIGN.CENTER, 0, 0)


def radioTune(freq):
    modeChange = False
    if len(freq) < 4:
        return
    else:
        fnum = freq[0:len(freq)-3]

    if freq[-3] == "M":
        fmhz = int(float(fnum) * 1000.0 / 10)
        fkhz = int(float(fnum) * 1000.0)
    elif freq[-3] == "k":
        fmhz = int(float(fnum) * 1.00 / 10)
        fkhz = int(float(fnum) * 1.00)
    else:
        return
    
    #print("fmhz:" + str(fmhz) + " fkhz: " + str(fkhz) + " freq: " + freq)

    newMode = radio.getModeIdx(fkhz)
    if newMode == 0:                 # Frequency in FM Mode
        if radio.modeIdx != 0:       # Change from AM to FM Mode
            mutesp.value(1)
            mutehp.value(1)
            radio.POWER_DOWN()
            radio.FMPOWER_UP()
            modeChange = True
        radio.mute()
        radio.modeIdx = newMode
        radio.setFMDeEmphasis()
        radio.FM_SEEK_BAND_BOTTOM(int(radio.mode[newMode][1] / 10))
        radio.FM_SEEK_BAND_TOP(int(radio.mode[newMode][2] / 10))
        radio.FM_SEEK_FREQ_SPACING(radio.mode[newMode][3])
        radio.FM_TUNE_FREQ(fmhz)
        radio.setVolume(volumeSlider.get_value())
        radio.unmute()
        if modeChange == True:
            time.sleep(1)
            mutehp.value(0)
            time.sleep(0.6)
            mutesp.value(0)
        kbdTextArea.set_text(freq)
        modeBtnLabel.set_text(radio.mode[newMode][0])
        st.changeFM()
        st.changebg(5)
    elif newMode > 0: # Frequency in AM Mode
        if radio.modeIdx == 0 or radio.modeIdx == -1:       # switch from FM to AM mode
            mutesp.value(1)
            mutehp.value(1)
            radio.POWER_DOWN()
            radio.AMPOWER_UP()
            modeChange = True
        radio.mute()
        radio.modeIdx = newMode
        radio.AM_SEEK_BAND_BOTTOM(int(radio.mode[newMode][1]))
        radio.AM_SEEK_BAND_TOP(int(radio.mode[newMode][2]))
        radio.AM_SEEK_FREQ_SPACING(radio.mode[newMode][3])
        radio.AM_TUNE_FREQ(fkhz)
        radio.setVolume(volumeSlider.get_value())
        radio.unmute()
        if modeChange == True:
            time.sleep(1)
            mutehp.value(0)
            time.sleep(0.6)
            mutesp.value(0)
        kbdTextArea.set_text(freq)
        modeBtnLabel.set_text(radio.mode[newMode][0])
        st.changeAM()
        if fkhz <= 1602:
            st.changebg(2)
        else:
            st.changebg(1)
    
radio = Si4735(i2c, 22)
configFileName = "config.json"
with open(configFileName, 'r') as f: config = json.load(f)
radioTune(config["Freq"])

radio.setVolume(config["Vol"])
volumeSlider.set_value(config["Vol"], lv.ANIM.OFF)
volumeSliderLabel.set_text("Vol {:d}".format(config["Vol"]))

def updateScreen(timer1):
    if radio.modeIdx == 0:
        radio.FM_TUNE_STATUS()
        radio.FM_RSQ_STATUS()
        if kbdTextArea.get_text() != radio.getFmFreqStr():
            kbdTextArea.set_text(radio.getFmFreqStr())
    else:
        radio.AM_TUNE_STATUS()
        radio.AM_RSQ_STATUS()
        if kbdTextArea.get_text() != radio.getAmFreqStr():
            kbdTextArea.set_text(radio.getAmFreqStr())

    labelSignal.set_text(str(radio.rssi) + "dBuV")
    if radio.modeIdx > 0:
        if radio.rssi >= 0 and radio.rssi <=  1: smeterBar.set_value(0, lv.ANIM.OFF)   # S0
        elif radio.rssi >  1 and radio.rssi <=  1: smeterBar.set_value(10, lv.ANIM.OFF)  # S1
        elif radio.rssi >  2 and radio.rssi <=  3: smeterBar.set_value(20, lv.ANIM.OFF)  # S2
        elif radio.rssi >  3 and radio.rssi <=  4: smeterBar.set_value(30, lv.ANIM.OFF)  # S3
        elif radio.rssi >  4 and radio.rssi <= 10: smeterBar.set_value(40, lv.ANIM.OFF)  # S4
        elif radio.rssi > 10 and radio.rssi <= 16: smeterBar.set_value(50, lv.ANIM.OFF)  # S5
        elif radio.rssi > 16 and radio.rssi <= 22: smeterBar.set_value(60, lv.ANIM.OFF)  # S6
        elif radio.rssi > 22 and radio.rssi <= 28: smeterBar.set_value(70, lv.ANIM.OFF)  # S7
        elif radio.rssi > 28 and radio.rssi <= 34: smeterBar.set_value(80, lv.ANIM.OFF)  # S8
        elif radio.rssi > 34 and radio.rssi <= 44: smeterBar.set_value(90, lv.ANIM.OFF)  # S9
        elif radio.rssi > 44 and radio.rssi <= 54: smeterBar.set_value(100, lv.ANIM.OFF)  # S9 +10
        elif radio.rssi > 54 and radio.rssi <= 64: smeterBar.set_value(110, lv.ANIM.OFF)  # S9 +20
        elif radio.rssi > 64 and radio.rssi <= 74: smeterBar.set_value(120, lv.ANIM.OFF)  # S9 +30
        elif radio.rssi > 74 and radio.rssi <= 84: smeterBar.set_value(130, lv.ANIM.OFF)  # S9 +40
        elif radio.rssi > 84 and radio.rssi <= 94: smeterBar.set_value(140, lv.ANIM.OFF)  # S9 +50
        elif radio.rssi > 94:                      smeterBar.set_value(150, lv.ANIM.OFF)  # S9 +60
        elif radio.rssi > 95:                      smeterBar.set_value(160, lv.ANIM.OFF)  #>S9 +60
    if radio.modeIdx == 0:
        if radio.rssi >= 0 and radio.rssi <=  1: smeterBar.set_value(50, lv.ANIM.OFF)   # S0
        elif radio.rssi >  1 and radio.rssi <=  2: smeterBar.set_value(60, lv.ANIM.OFF)  # S1
        elif radio.rssi >  2 and radio.rssi <=  8: smeterBar.set_value(70, lv.ANIM.OFF)  # S2
        elif radio.rssi >  8 and radio.rssi <= 14: smeterBar.set_value(80, lv.ANIM.OFF)  # S3
        elif radio.rssi > 14 and radio.rssi <= 24: smeterBar.set_value(90, lv.ANIM.OFF)  # S4
        elif radio.rssi > 24 and radio.rssi <= 34: smeterBar.set_value(100, lv.ANIM.OFF)  # S5
        elif radio.rssi > 34 and radio.rssi <= 44: smeterBar.set_value(110, lv.ANIM.OFF)  # S6
        elif radio.rssi > 44 and radio.rssi <= 54: smeterBar.set_value(120, lv.ANIM.OFF)  # S7
        elif radio.rssi > 54 and radio.rssi <= 64: smeterBar.set_value(130, lv.ANIM.OFF)  # S8
        elif radio.rssi > 64 and radio.rssi <= 74: smeterBar.set_value(140, lv.ANIM.OFF)  # S9
        elif radio.rssi > 74:                      smeterBar.set_value(150, lv.ANIM.OFF)  # S9 +60
        elif radio.rssi > 76:                      smeterBar.set_value(160, lv.ANIM.OFF)  #>S9 +60

    labelSnr.set_text(str(radio.snr) + "dB")
    labelSTBLEND.set_text("Stereo " + str(radio.stblend) + "%")
    labelSTBLEND.set_style_bg_color(lv.color_make(255,255-radio.stblend,255-radio.stblend), lv.PART.MAIN | lv.STATE.DEFAULT )
    if volumeSlider.get_value() != config["Vol"]:
        config["Vol"] = volumeSlider.get_value()
        with open(configFileName, 'w') as f: json.dump(config, f)
    if kbdTextArea.get_text() != config["Freq"] and len(kbdTextArea.get_text()) > 3:
        config["Freq"] = kbdTextArea.get_text()
        with open(configFileName, 'w') as f: json.dump(config, f)
    if radio.fast == True:
        if radio.modeIdx == 0:
            radio.FM_TUNE_FREQ(radio.freq)
        else:
            radio.AM_TUNE_FREQ(radio.freq)

timer1 = lv.timer_create(updateScreen, 700, None)