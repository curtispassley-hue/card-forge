"""Coalesced preview worker: show completed frames while keeping only the next rotation."""
import queue
import threading
import tkinter as tk
from PIL import ImageTk
from .theme import studio_backdrop, MUTED


class PreviewRenderer:
    def __init__(self, canvas):
        self.canvas=canvas; self.epoch=0; self.parts=None; self.pending=None; self.busy=False
        self.closed=False; self.poll_id=None; self.last_error=''
        canvas.bind('<Destroy>',self._close,add='+')

    def _close(self, event=None):
        if event is not None and event.widget!=self.canvas:return
        self.closed=True; self.cancel()

    def cancel(self):
        self.epoch+=1; self.pending=None; self.parts=None
        if self.poll_id is not None:
            try:self.canvas.after_cancel(self.poll_id)
            except tk.TclError:pass
            self.poll_id=None
        self.busy=False

    def request(self, parts, yaw, pitch, face_down=False, interactive=False):
        if self.closed:return
        if parts is not self.parts:
            self.cancel();self.parts=parts
        size=max(100,self.canvas.winfo_width()),max(100,self.canvas.winfo_height())
        self.pending=(parts,size,yaw,pitch,face_down,interactive)
        if not self.busy:self._start()

    def _start(self):
        if self.closed or self.pending is None:return
        parts,size,yaw,pitch,face_down,interactive=self.pending
        epoch=self.epoch
        self.pending=None;self.busy=True;results=queue.Queue()
        def work():
            from .product_ui import mesh_preview
            try:
                image=mesh_preview(parts,*size,yaw,pitch,face_down=face_down,
                    background=studio_backdrop(*size),max_size=(360,240) if interactive else (800,600),
                    cancelled=lambda:self.closed or epoch!=self.epoch)
                results.put((image,''))
            except Exception as exc:results.put((None,str(exc)))
        def poll():
            self.poll_id=None
            if self.closed:return
            try:image,error=results.get_nowait()
            except queue.Empty:self.poll_id=self.canvas.after(20,poll);return
            self.busy=False
            if epoch==self.epoch:
                self.last_error=error
                if image is not None:
                    c=self.canvas;c.delete('all');c.image_ref=ImageTk.PhotoImage(image)
                    c.create_image(0,0,anchor='nw',image=c.image_ref)
                    c.create_text(12,12,anchor='nw',text='Assembly preview • drag to rotate',fill=MUTED,font=('Segoe UI',10,'bold'))
            if self.pending is not None:self._start()
        threading.Thread(target=work,daemon=True,name='CardForge preview').start()
        self.poll_id=self.canvas.after(20,poll)
