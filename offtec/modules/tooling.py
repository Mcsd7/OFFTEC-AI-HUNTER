import os, queue, re, shutil, subprocess, threading, time

TOOL_NAMES=("nmap","sqlmap","nuclei","httpx","whatweb","subfinder","dnsx","wafw00f")
SENSITIVE=re.compile(r"(?i)(authorization|api[_-]?key|access[_-]?token|password|secret)(\s*[:=]\s*)([^\s,;]+)")

def sanitize(text): return SENSITIVE.sub(r"\1\2[REDACTED]",text)

def sanitize_value(value):
    if isinstance(value,str): return sanitize(value)
    if isinstance(value,list): return [sanitize_value(x) for x in value]
    if isinstance(value,dict): return {k:sanitize_value(v) for k,v in value.items()}
    return value

def inventory(): return {name:shutil.which(name) for name in TOOL_NAMES}

def run_tool(args, timeout=90, cancel=None, cwd=None, max_output=1_000_000, progress=None):
    """Argument-vector-only execution with bounded time, output and cancellation."""
    if not args or not os.path.isabs(shutil.which(args[0]) or ""):
        raise FileNotFoundError(args[0] if args else "tool")
    proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,cwd=cwd,text=True,errors="replace",bufsize=1)
    chunks=[]; size=0; start=time.monotonic(); lines=queue.Queue()
    def drain():
        try:
            for line in proc.stdout: lines.put(line)
        finally: lines.put(None)
    reader=threading.Thread(target=drain,daemon=True); reader.start()
    try:
        done=False
        while proc.poll() is None or not done:
            if progress: progress(min(80,10+int((time.monotonic()-start)/timeout*70)),"external tool running")
            if cancel and cancel.is_set():
                proc.terminate()
                try: proc.wait(2)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
                raise InterruptedError("cancelled")
            if time.monotonic()-start>timeout:
                proc.terminate()
                try: proc.wait(2)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
                raise TimeoutError(f"{args[0]} timed out")
            try: line=lines.get(timeout=.05)
            except queue.Empty: continue
            if line is None: done=True; continue
            if line:
                size+=len(line.encode("utf-8",errors="replace"))
                if size<=max_output: chunks.append(line)
                else:
                    proc.terminate(); proc.wait(timeout=2)
                    raise RuntimeError("tool output exceeded size limit")
        return {"returncode":proc.returncode,"output":sanitize("".join(chunks)),"command":args[0],"elapsed":round(time.monotonic()-start,2)}
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()
