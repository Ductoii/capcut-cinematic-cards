"""Local Silero v6 inference on bounded batches; see assets/PROVENANCE.md."""
from pathlib import Path

import numpy as np

from .process import run,check_cancel


def detect(path,out,cancelled=lambda:False,progress=lambda *a:None):
    import onnxruntime as ort
    out=Path(out);out.mkdir(parents=True,exist_ok=True);mono=out/'vad.f32'
    with mono.open('wb') as f:
        run(['ffmpeg','-v','error','-i',path,'-vn','-ac','1','-ar','16000','-f','f32le','-'],stdout=f,cancelled=cancelled)
    audio=np.memmap(mono,dtype='<f4',mode='r');length=len(audio)
    opts=ort.SessionOptions();opts.intra_op_num_threads=1;opts.inter_op_num_threads=1
    model=ort.InferenceSession(str(Path(__file__).parent/'assets/silero_vad.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
    h=np.zeros((1,1,128),np.float32);c=h.copy();previous=np.zeros(64,np.float32);probs=[]
    total=(length+511)//512
    for index in range(0,total,4000):
        check_cancel(cancelled);n=min(4000,total-index)
        data=np.zeros(n*512,np.float32);part=audio[index*512:min(length,(index+n)*512)]
        data[:len(part)]=np.clip(part,-1,1);chunks=data.reshape(n,512)
        context=np.vstack((previous[None,:],chunks[:-1,-64:]))
        previous=chunks[-1,-64:].copy()
        output,h,c=model.run(None,dict(input=np.concatenate((context,chunks),axis=1),h=h,c=c))
        probs.extend(np.asarray(output).reshape(-1).tolist());progress('speech',index+n,total)
    del audio
    spans=[];start=None;quiet=None
    for i,p in enumerate(probs):
        t=i*512/16000
        if start is None and p>=.5:start=t;quiet=None
        elif start is not None:
            if p>=.35:quiet=None
            elif quiet is None:quiet=t
            if quiet is not None and t-quiet>=.35:
                if quiet-start>=.25:spans.append([max(0,start-.08),min(length/16000,quiet+.08)])
                start=quiet=None
            elif t-start>=8:
                spans.append([max(0,start-.08),t]);start=t;quiet=None
    if start is not None and length/16000-start>=.25:spans.append([max(0,start-.08),length/16000])
    result=[]
    for left,right in spans:
        if result and left<result[-1]['end']:left=result[-1]['end']
        if right-left>=.25:result.append(dict(id=f'speech-{len(result)+1:05d}',start=round(left,6),end=round(right,6)))
    return result
