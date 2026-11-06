"""Real PTY regression: exercise the production raw-TTY reader, not a mock."""
import os
import pty
import select
import subprocess
import sys
import time

import pytest

from offtec.interface.keyboard import decode_escape


@pytest.mark.parametrize("sequence,expected", [
    (b"\x1b[A", "up"), (b"\x1b[B", "down"),
    (b"\x1b[C", "right"), (b"\x1b[D", "left"),
    (b"\x1bOA", "up"), (b"\x1bOB", "down"),
    (b"\x1bOC", "right"), (b"\x1bOD", "left"),
    (b"\x1b[1;2A", "up"), (b"\x1b[1;5D", "left"),
    (b"\x1b[Z", "shift_tab"), (b"\x1b", "esc"),
])
def test_escape_sequence_decoder(sequence, expected):
    assert decode_escape(sequence) == expected


@pytest.mark.parametrize("sequence,expected", [
    (b"\x1b[A","up"),(b"\x1b[B","down"),(b"\x1b[C","right"),(b"\x1b[D","left"),
    (b"\x1bOA","up"),(b"\x1bOB","down"),(b"\x1bOC","right"),(b"\x1bOD","left"),
    (b"\x1b[1;2A","up"),(b"\t","tab"),(b"\x1b[Z","shift_tab"),
    (b"\r","enter"),(b"\x03","ctrlc"),(b"\x1b","esc"),(b"j","j"),(b"k","k"),
])
def test_production_key_reader_on_pseudo_terminal(sequence,expected):
    master, slave = pty.openpty()
    command = [sys.executable, "-u", "-c",
        "from offtec.interface.keyboard import keypress; print('READY', flush=True); print('RESULT:'+keypress(), flush=True)"]
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
    os.close(slave)
    output = bytearray()
    deadline = time.monotonic() + 4
    try:
        while b"READY\r\n" not in output and time.monotonic() < deadline:
            if select.select([master], [], [], .1)[0]:
                try: output.extend(os.read(master, 4096))
                except OSError: pass
        assert b"READY\r\n" in output
        # Let the child switch the TTY to raw mode before sending the split key.
        time.sleep(.05)
        chunks=(b"\x1b",b"[",b"B") if sequence==b"\x1b[B" else (sequence,)
        for part in chunks:
            os.write(master, part)
            if len(chunks)>1: time.sleep(.035)
        while b"RESULT:" not in output and time.monotonic() < deadline:
            if select.select([master], [], [], .1)[0]:
                try: output.extend(os.read(master, 4096))
                except OSError: pass
        process.wait(timeout=2)
        assert ("RESULT:"+expected).encode() in output
        assert b"^[[" not in output  # no tail bytes leaked back into cooked terminal mode
    finally:
        if process.poll() is None: process.kill(); process.wait()
        os.close(master)


def test_real_menu_choice_uses_ss3_arrow_and_enter_in_pty():
    master, slave = pty.openpty()
    code = (
        "from offtec.interface.app import App; from offtec.core.i18n import Translator; "
        "app=App.__new__(App); app.console=None; app.tr=Translator('pt_BR'); "
        "print('READY',flush=True); print('SELECTED:'+str(app.choose('Menu',[('Primeira','first'),('Segunda','second')])),flush=True)"
    )
    env=os.environ.copy(); env["TERM"]="xterm-256color"
    process = subprocess.Popen([sys.executable,"-u","-c",code],stdin=slave,stdout=slave,stderr=slave,env=env,close_fds=True)
    os.close(slave)
    output=bytearray(); deadline=time.monotonic()+5
    try:
        while b"READY\r\n" not in output and time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: output.extend(os.read(master,4096))
                except OSError: pass
        assert b"READY\r\n" in output
        time.sleep(.05)
        os.write(master,b"\x1bOB")  # Terminfo/application-cursor form: SS3 Down.
        time.sleep(.08)
        os.write(master,b"\r")
        while b"SELECTED:" not in output and time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: output.extend(os.read(master,4096))
                except OSError: pass
        process.wait(timeout=2)
        assert b"SELECTED:second\r\n" in output
    finally:
        if process.poll() is None: process.kill(); process.wait()
        os.close(master)


def test_input_field_keeps_readline_arrow_cursor_editing():
    master,slave=pty.openpty()
    code=("from offtec.interface.app import App; app=App.__new__(App); "
          "print('READY',flush=True); print('VALUE:'+repr(app.input('text')),flush=True)")
    process=subprocess.Popen([sys.executable,"-u","-c",code],stdin=slave,stdout=slave,stderr=slave,close_fds=True)
    os.close(slave); output=bytearray(); deadline=time.monotonic()+5
    try:
        while b"READY\r\n" not in output and time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: output.extend(os.read(master,4096))
                except OSError: pass
        assert b"READY\r\n" in output
        time.sleep(.05)
        os.write(master,b"abc\x1b[Dx\r")
        while b"VALUE:" not in output and time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: output.extend(os.read(master,4096))
                except OSError: pass
        process.wait(timeout=2)
        assert b"VALUE:'abxc'\r\n" in output
    finally:
        if process.poll() is None: process.kill(); process.wait()
        os.close(master)


@pytest.mark.parametrize("key,expected", [(b"\x1b", "__chat_exit__"), (b"q", "__chat_exit__")])
def test_chat_input_can_exit_without_enter(key, expected):
    master,slave=pty.openpty()
    code=("from offtec.interface.app import App; from offtec.core.i18n import Translator; "
          "app=App.__new__(App); app.tr=Translator('en'); app.console=None; "
          "print('READY',flush=True); print('VALUE:'+app.chat_input('Message'),flush=True)")
    process=subprocess.Popen([sys.executable,"-u","-c",code],stdin=slave,stdout=slave,stderr=slave,close_fds=True)
    os.close(slave); output=bytearray(); deadline=time.monotonic()+5
    try:
        while b"READY\r\n" not in output and time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: output.extend(os.read(master,4096))
                except OSError: pass
        assert b"READY\r\n" in output
        time.sleep(.05); os.write(master,key)
        while b"VALUE:" not in output and time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: output.extend(os.read(master,4096))
                except OSError: pass
        process.wait(timeout=2)
        assert ("VALUE:"+expected).encode() in output
    finally:
        if process.poll() is None: process.kill(); process.wait()
        os.close(master)


def test_application_main_menu_dispatches_ss3_and_csi_arrows():
    master,slave=pty.openpty()
    code=(
        "from offtec.interface.app import App,MENU; from offtec.interface.navigation import NavigationState; "
        "classobj=type('Closer',(),{'shutdown':lambda self:None,'close':lambda self:None}); "
        "app=App.__new__(App); app.navigation=NavigationState(len(MENU),3); app.tab=0; app.panel_focus=False; "
        "app.panel_tab=0; app.panel_actions=['menu.projects','task.title','menu.settings']; "
        "app.tasks=classobj(); app.codex=classobj(); "
        "app.render=lambda:print('STATE:'+str(app.tab)+':'+str(int(app.panel_focus))+':'+str(app.panel_tab),flush=True); "
        "app.dispatch=lambda item:print('DISPATCH:'+item,flush=True); app.main()"
    )
    env=os.environ.copy(); env["TERM"]="xterm-256color"
    process=subprocess.Popen([sys.executable,"-u","-c",code],stdin=slave,stdout=slave,stderr=slave,env=env,close_fds=True)
    os.close(slave); output=bytearray(); deadline=time.monotonic()+5
    try:
        while b"STATE:0:0:0\r\n" not in output and time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: output.extend(os.read(master,4096))
                except OSError: pass
        assert b"STATE:0:0:0\r\n" in output
        time.sleep(.05)
        os.write(master,b"\x1bOB")  # SS3 Down
        time.sleep(.05)
        os.write(master,b"\x1b[C")  # CSI Right; both should advance one row.
        time.sleep(.05)
        os.write(master,b"\r")
        time.sleep(.05)
        os.write(master,b"\t")
        time.sleep(.05)
        os.write(master,b"\x1bOB")
        time.sleep(.05)
        os.write(master,b"\x1b[Z")  # Shift+Tab returns focus to the menu.
        time.sleep(.05)
        os.write(master,b"\x03")  # safe main-loop exit
        while process.poll() is None and time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: output.extend(os.read(master,4096))
                except OSError: pass
        process.wait(timeout=2)
        assert b"STATE:2:1:1\r\n" in output
        assert b"STATE:2:0:1\r\n" in output
        assert b"DISPATCH:menu.recon\r\n" in output
    finally:
        if process.poll() is None: process.kill(); process.wait()
        os.close(master)
