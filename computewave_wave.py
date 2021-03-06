#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   measure_routine.py
@Time    :   2020/02/20 10:24:45
@Author  :   sk zhao 
@Version :   1.0
@Contact :   2396776980@qq.com
@License :   (C)Copyright 2017-2018, Liugroup-NLPR-CASIA
@Desc    :   None
'''

# here put the import lib
import numpy as np, time, pickle, datetime
from easydl import clear_output
from qulab.wavepoint import WAVE_FORM as WF
from qulab.waveform import CosPulseDrag, Expi, DC, Step, Gaussian, CosPulse
from qulab import waveform_new as wn
from tqdm import tqdm_notebook as tqdm
import asyncio, inspect
from qulab import imatrix as mx
import functools


t_list = np.linspace(0,100000,250000)
t_new = np.linspace(-90000,10000,250000)*1e-9
t_range = (-90e-6, 10e-6)
sample_rate = 2.5e9

################################################################################
# 收集变量
################################################################################

def saveStatus(fname='D:/status.obj'):
    import sys
    
    status = {}
    
    for k in filter(
        lambda s: s[0] != '_' and not callable(globals()[s]) and
        not isinstance(globals()[s], type(sys)) and not s in ['In', 'Out'],
        globals().keys()):
        try:
            status[k] = pickle.dumps(globals()[k])
        except:
            print(k, type(globals()[k]))
            
    with open(fname, 'wb') as f:
         pickle.dump(status, f)
    
def loadStatus(fname='D:/status.obj'):
    with open(fname, 'rb') as f:
        status = pickle.load(f)
    
    for k, v in status.items():
        globals()[k] = pickle.loads(v)

################################################################################
# 函数参数解析及赋值
################################################################################

async def funcarg(f,qubit,**kws):

    bit = dict(qubit.asdict())
    insp = inspect.getfullargspec(f)
    # paras, defaults = insp[0][::-1], insp[3]
    paras, defaults = insp[0], insp[3]
    status = {}
    for j,i in enumerate(paras):
        if i in kws:
            status[i] = kws[i]
        else:
    #         if defaults and j < len(defaults):
    #             ptype = type(defaults[-j-1])
    #             status[i] = bit[i]
            if i in bit:
                status[i] = bit[i]
    # print(status)
    pulse = await f(**status)
    return pulse
    
################################################################################
# 收集awg波形名字
################################################################################

def Collect_Waveform(dictname,kind):
    
    def decorator(func):
        def wrapper(*args, **kw):
            if asyncio.iscoroutinefunction(func):
                loop = asyncio.get_event_loop()
                name_list = loop.run_until_complete(func(*args, **kw))
                dictname[kind] = name_list
            else:
                return func(*args, **kw)
        return wrapper
    return decorator

################################################################################
# 创建波形及sequence
################################################################################

async def create_wavelist(measure,kind,para):
    awg,name,n_wave,length,mode = para
    if kind in measure.wave:
        print('Warning: kind has already existed')
    @Collect_Waveform(measure.wave,kind)
    async def create_waveformlist(awg,name,n_wave,length,mode):
        name_list = []
        name_sub_list = []
        for k, i in enumerate(name):
            name_collect = []
            for j in range(1,n_wave+1):
                if mode == 'hbroadcast':
                    if k == 0:
                        name_sub = ''.join((kind,'_sub','%d'%j))
                        await awg.create_sequence(name_sub,2,2)
                        name_sub_list.append(name_sub)
                name_w = ''.join((kind,'_',i,'%d'%j))
                name_collect.append(name_w)
                await awg.create_waveform(name=name_w, length=length, format=None) 
            name_list.append(name_collect)
        name_list.append(name_sub_list)
        return name_list
    return create_waveformlist(*para)

################################################################################
# 询问AWG状态
################################################################################

async def couldRun(awg,chlist=None,namelist=None):
    await awg.run()
    if chlist != None:
        for j, i in enumerate(chlist):
            if namelist != None:
                await awg.use_waveform(name=namelist[j],ch=i)
            await awg.output_on(ch=i)
    # time.sleep(5)
    while True:
        time.sleep(0.5)
        x = await awg.run_state()
        if x == 1 or x == 2:
            break

################################################################################
# awg清理sequence
################################################################################

async def clearSeq(measure,awg):
    if isinstance(awg, list):
        for i in awg:
            await measure.awg[i].stop()
            await measure.awg[i].write('*WAI')
            for j in range(8):
                await measure.awg[i].output_off(ch=j+1)
            await measure.awg[i].clear_sequence_list()
    elif isinstance(awg, str):
        await measure.awg[awg].stop()
        await measure.awg[awg].write('*WAI')
        for j in range(8):
            await measure.awg[awg].output_off(ch=j+1)
        await measure.awg[awg].clear_sequence_list()
    else:
        await awg.stop()
        await awg.write('*WAI')
        for j in range(8):
            await awg.output_off(ch=j+1)
        await awg.clear_sequence_list()
    # measure.wave = {}

################################################################################
# awg载入sequence
################################################################################

async def awgchmanage(awg,seqname,ch):
    await awg.stop()
    await awg.use_sequence(seqname,channels=ch)
    time.sleep(5)
    # await awg.query('*OPC?')
    for i in ch:
        await awg.output_on(ch=i)
    await couldRun(awg)
    return

################################################################################
# awg生成并载入waveform
################################################################################

async def genwaveform(awg,wavname,ch,t_list=t_list):
    # t_list = measure.t_list
    await awg.stop()
    for j, i in enumerate(wavname):
        await awg.create_waveform(name=i, length=len(t_list), format=None)
        await awg.use_waveform(name=i,ch=ch[j])
        await awg.write('*WAI')
        await awg.output_on(ch=ch[j])

################################################################################
# awg生成子sequence
################################################################################

async def subSeq(measure,awg,subkind,wavename):
    # for j, i in enumerate(wavename,start=1):
    await awg.set_sequence_step(subkind,wavename,1)
    await awg.set_sequence_step(subkind,['zero','zero'],2,goto='FIRST',repeat=210) #####repeat乘以zero的长度就是pad的时间长度
    # await awg.create_sequence(subkind,2,8)
    # subkind = ''.join(('sub_',subkind))
    # await create_wavelist(measure,subkind,(awg,['I','Q'],lensubseq,len(measure.t_list)))
    # name = np.array(measure.wave[subkind])
    # for i, j in enumerate(wavename,start=1):
    #     await awg.set_sequence_step(subkind,j,i,wait='ATR',goto='NEXT',repeat=1,jump=('OFF','NEXT'))

################################################################################
# 生成Sequence
################################################################################

async def genSeq(measure,awg,kind,mode='hbroadcast'):
    await awg.stop()
    await awg.create_waveform(name='zero', length=2500, format=None)
    
    if mode == 'vbroadcast':
        await awg.create_sequence(kind,(len(measure.wave[kind][0])+1),2)
        await ats_setup(measure.ats,measure.delta,l=measure.readlen,repeats=len(measure.wave[kind][0]),mode='vbroadcast')
        wait = 'ATR' if awg == measure.awg['awg_trig'] else 'ATR'
        for j,i in enumerate(measure.wave[kind][:2],start=1):
            await awg.set_seq(i,1,j,seq_name=kind,wait=wait)
            # for k in np.arange((len(i)+2),1001):
            #     await awg.write('SLIS:SEQ:STEP%d:TASS%d:WAV "%s","%s"' %(k, j, kind, 'zero'))
    if mode == 'hbroadcast':
        await awg.create_sequence(kind,(len(measure.wave[kind][0])),2)
        await ats_setup(measure.ats,measure.delta,l=measure.readlen,repeats=measure.repeat,mode='hbroadcast')
        await awg.create_sequence('zero_sub',1,2)
        await awg.set_sequence_step('zero_sub',['zero','zero'],1)
        name_sub_list = measure.wave[kind][-1]
        wavenameIQ = np.array(measure.wave[kind][0:2])
        for j, i in enumerate(name_sub_list,start=1):
            await subSeq(measure,awg,i,wavenameIQ[:,(j-1)])
            goto = 'FIRST' if j == len(name_sub_list) else 'NEXT'
            await awg.set_sequence_step(kind,i,j,wait='ATR',goto=goto,repeat='INF',jump=('BTR',goto))
        # for k in np.arange((len(name_sub_list)+1),1001):
        #     await awg.set_sequence_step(kind,'zero_sub',int(k))
            # for l in range(2):
            #     await awg.write('SLIS:SEQ:STEP%d:TASS%d:WAV "%s","%s"' %(k, (l+1), kind, 'zero'))

################################################################################
# 打包sequence
################################################################################

async def gen_packSeq(measure,kind,awg,name,steps,readseq=True,mode='hbroadcast'):
    if measure.mode != mode or measure.steps != steps:
        measure.mode = mode
        measure.steps = steps
        await clearSeq(measure,awg)
        await clearSeq(measure,'awgread')
    await create_wavelist(measure,kind,(awg,name,steps,len(measure.t_list),mode))
    await genSeq(measure,awg,kind,mode=mode)
    if readseq:
        measure.wave['Read'] = [['Readout_I']*steps,['Readout_Q']*steps,['Read_sub']*steps]
        await measure.awg['awgread'].create_sequence('Read_sub',2,2)
        # await readSeq(measure,measure.awg['awgread'],'Read',[1,5])
        await genSeq(measure,measure.awg['awgread'],'Read',mode=mode)
        await awgchmanage(measure.awg['awgread'],'Read',[1,5])
        # await ats_setup(measure.ats,measure.delta,l=measure.readlen,repeats=steps,awg=1)
        # await ats_setup(measure.ats,measure.delta,l=measure.readlen,repeats=measure.repeat,awg=1)
        
################################################################################
# awgDC波形
################################################################################

async def awgDC(awg,wavname,volt):
    await awg.stop()
    # init = DC(offset=-0.7, length=100e-6, range=(0,1))*0 + volt
    # wav = init
    init  = ((Step(2e-9)<<3000e-9) - Step(2e-9))*volt
    wav = (init >> 2250e-9)
    wav.set_range(*t_range)
    points = wav.generateData(sample_rate)
    await awg.update_waveform(points,wavname)

################################################################################
# Z波形矫正
################################################################################

def predistort(waveform, sRate, zCali):
    """Predistort input waveform.
    Parameters
    ----------
        waveform : complex numpy array
            Waveform data to be pre-distorted
        zCali: [2.55e-9, -28e-3, 8.02e-9, -28e-3, 101.5e-9, -14.5e-3,369.7e-9,-6.2e-3]
    Returns
    -------
    waveform : complex numpy array
        Pre-distorted waveform
    """
    dt = 1 / sRate
    wf_size = len(waveform)
    tau1, A1, tau2, A2, tau3, A3, tau4, A4, tau5, A5 = zCali
    # print('tau:', tau1, A1, tau2, A2, tau3, A3, tau4, A4, tau5, A5)
    # pad with zeros at end to make sure response has time to go to zero
    # pad_time = 6 * max([tau1, tau2, tau3])
    pad_time = 4e-6  # 这里默认改为增加4us的pad，返回时舍去1us，保留3us拖尾
    pad_size = round(pad_time / dt)
    pad_size_2 = round(3e-6 / dt)  # 保留的点数
    padded_zero = np.zeros(pad_size)
    padded = np.append(waveform,padded_zero)

    Y = np.fft.rfft(padded, norm='ortho')

    omega = 2 * np.pi * np.fft.rfftfreq(wf_size+pad_size, dt)
    H = (1 + (1j * A1 * omega * tau1) / (1j * omega * tau1 + 1) +
         (1j * A2 * omega * tau2) / (1j * omega * tau2 + 1) +
         (1j * A3 * omega * tau3) / (1j * omega * tau3 + 1) +
         (1j * A4 * omega * tau4) / (1j * omega * tau4 + 1)+
         (1j * A5 * omega * tau5) / (1j * omega * tau5 + 1))

    Yc = Y / H
    yc = np.fft.irfft(Yc, norm='ortho')
    # return yc[:wf_size]
    #这里返回增加了3us拖尾的序列
    return yc[:(wf_size+pad_size_2)]

################################################################################
# 更新波形
################################################################################
# @functools.lru_cache()
async def writeWave(awg,name,pulse,norm=False,t=t_new,mark=False):

    # t = np.linspace(-90000,10000,25000)*1e-9
    await awg.stop()
    if len(pulse) == 4:
        wav_I, wav_Q, mrk1, mrk2 = pulse
        I, Q = wav_I(t), wav_Q(t)
        # I, Q = pulse
        if norm:
            I, Q = I / np.max(np.abs(I)), Q / np.max(np.abs(Q))
        await awg.update_waveform(I, name = name[0])
        await awg.update_waveform(Q, name = name[1])
        if mark:
            # for i, j in enumerate(mark):
            mrk1 = [i(t) for i in mrk1]
            mrk2 = [i(t) for i in mrk2]
            await awg.update_marker(name[0],*mrk1)
            await awg.update_marker(name[1],*mrk2)
    if len(pulse) == 1:
        wave = pulse[0]
        # t = np.linspace(-90000,7000,242500)*1e-9
        # wave = pulse
        wave = wave(t)
        # wave = predistort(wave,2.5e9,[2.55e-9, -28e-3, 8.02e-9, -28e-3, 101.5e-9, -14.5e-3,369.7e-9,-6.2e-3,5e-9,-5e-3])
        await awg.update_waveform(wave, name = name[0])

################################################################################
# 波包选择
################################################################################

def whichEnvelope(pi_len,envelope,num):
    if envelope == 'hanning':
        if num == 1:
            return wn.hanning(pi_len) << pi_len/2
        if num == 2:
            return (wn.hanning(pi_len) << pi_len/2) + (wn.hanning(pi_len) << 1.5*pi_len)
    if envelope == 'hamming':
        if num == 1:
            return wn.hamming(pi_len) << pi_len/2
        if num == 2:
            return (wn.hamming(pi_len) << pi_len/2) + (wn.hamming(pi_len) << 1.5*pi_len)
    if envelope == 'gaussian':
        if num == 1:
            return wn.gaussian(pi_len) << pi_len/2
        if num == 2:
            return (wn.gaussian(pi_len) << pi_len/2) + (wn.gaussian(pi_len) << 1.5*pi_len)
    if envelope == 'square':
        return wn.square(pi_len) << pi_len/2


################################################################################
# 设置采集卡
################################################################################

async def ats_setup(ats,delta,l=1000,repeats=500,mode=None):
    await ats.set(n=l,repeats=repeats,mode=mode,
                           f_list=delta,
                           maxlen=512,
                           ARange=1.0,
                           BRange=1.0,
                           trigLevel=0.5,
                           triggerDelay=0,
                           triggerTimeout=0,
                           bufferCount=512)

################################################################################
# 读出混频
################################################################################

async def modulation_read(measure,delta,readlen=1100,repeats=512,phase=0.0,rname=['Readout_I','Readout_Q']):
    t_list, ats, awg = measure.t_list, measure.ats, measure.awg['awgread']
    await awg.stop()
    readamp = measure.readamp
    twidth, n, measure.readlen, measure.repeat = readlen, len(delta), readlen, (repeats // 64 + 1) * 64
    wavelen = (twidth // 64) * 64
    if wavelen < twidth:
        wavelen += 64
    measure.wavelen = int(wavelen) 

    await genwaveform(awg,rname,[1,5])
    
    ringup = 100
    # pulse1 = wn.square((wavelen-ringup)/1e9) >> ((wavelen+ringup)/ 1e9 / 2)
    pulse1 = wn.square(wavelen/1e9) >> (wavelen/ 1e9 / 2 + ringup / 1e9)
    pulse2 = wn.square(ringup/1e9)>>(ringup/2/1e9)
    pulse = readamp*pulse1+pulse2

    mrkp1 = wn.square(25000e-9) << (25000e-9 / 2 + 500e-9)
    mrkp2 = wn.square(wavelen/1e9) >> (wavelen / 1e9 / 2 + 440 / 1e9 + ringup / 1e9)
    # mrkp3 = wn.square(4000/1e9) >> 1000/1e9
    mrkp4 = wn.square(5000/1e9) << (2500+84995)/1e9
    I, Q = wn.zero(), wn.zero()
    for i in delta:
        wav_I, wav_Q = wn.mixing(pulse,phase=phase,freq=i,ratioIQ=-1.0)
        I, Q = I + wav_I, Q + wav_Q
    I, Q = I / n, Q / n
    pulselist = I, Q, (mrkp2,), (mrkp4,mrkp4,mrkp1,mrkp4)
    await writeWave(awg,rname,pulselist,False,mark=True)
    await awg.setValue('Vpp',1.5*n,ch=1)
    await awg.setValue('Vpp',1.5*n,ch=5)
    await awg.write('*WAI')
    await ats_setup(ats,delta,l=readlen,repeats=repeats)
    await couldRun(awg)
    return pulselist

################################################################################
# 激励混频
################################################################################

async def modulation_ex(qubit,measure,w=20000e-9,delta_ex=[0],shift=0):
    t_list, awg = measure.t_list, measure.awg['awg132']
    wf, qname, n = WF(t_list), ['awg132_ch7','awg132_ch8'], len(delta_ex)
    await genwaveform(awg,qname,[7,8])
    pulse = wn.square(w) << (w / 2 + 200e-9+shift)
    await writeWave(awg,qname,(pulse,pulse,pulse,pulse),mark=True)
    await couldRun(awg)

################################################################################s
# Rabi波形
################################################################################

async def rabiWave(envelopename=['square',1],nwave=1,amp=1,pi_len=75e-9,shift=0,delta_ex=110e6,phase=0,\
    phaseDiff=0,DRAGScaling=None,timing={'z>xy':0,'read>xy':0}):
    shift += timing['read>xy']
    wave = whichEnvelope(pi_len,*envelopename) << shift
    wave *= amp
    mwav = wn.square(2*pi_len) << (pi_len+shift)
    pulse, mpulse = wn.zero(), wn.zero()
    for i in range(nwave):
        pulse += (wave << envelopename[1]*i*pi_len)
        mpulse += (mwav << envelopename[1]*i*pi_len)
    wav_I, wav_Q = wn.mixing(pulse,phase=phase,freq=delta_ex,ratioIQ=-1.0,phaseDiff=phaseDiff,DRAGScaling=DRAGScaling)

    return wav_I, wav_Q, mpulse, mpulse

################################################################################s
# Rabi_seq
################################################################################

async def Rabi_sequence(qubit,measure,kind,v_or_t,arg,**paras):
    # print(v_or_t,arg,paras)
    awg= measure.awg[qubit.inst['ex_awg']]
    await awg.stop()
    for j,i in enumerate(tqdm(v_or_t,desc=''.join(('Rabi_',kind)))):
        paras[arg] = i
        name_ch = [measure.wave[kind][0][j],measure.wave[kind][1][j]]
        pulse = await funcarg(rabiWave,qubit,**paras)
        await writeWave(awg,name_ch,pulse,mark=False)

################################################################################
# pipulseDetune波形
################################################################################

async def pipulseDetunewave(measure,awg,pilen,n,alpha,delta,name_ch,phaseDiff=0):
    shift = 200/1e9
    pilen = pilen / 1e9
    envelope = whichEnvelope(measure.envelopename)
    I, Q, mrk1, mrk2 = wn.zero(), wn.zero(), wn.zero(), wn.zero()
    for i in [np.pi,0]*n:
        pulse = (envelope(pilen) << (0.5*pilen+shift)) + (envelope(pilen) << (1.5*pilen + shift))
        shift += 2*pilen
        wav_I, wav_Q = wn.mixing(pulse,phase=i,freq=delta,phaseDiff=phaseDiff,ratioIQ=-1.0,DRAGScaling=alpha)
        I, Q = I+wav_I, Q+wav_Q
    await writeWave(awg,name_ch,(I,Q,mrk1,mrk2))
    return I,Q,mrk1,mrk2
    

################################################################################
# Ramsey及SpinEcho,CPMG, PDD波形
################################################################################

async def coherenceWave(envelopename=['square',1],t_run=0,amp=1,pi_len=75e-9,nwave=0,seqtype='CPMG',\
    detune=3e6,shift=0e-9,delta_ex=110e6,phaseDiff=0.0,DRAGScaling=None,timing={'z>xy':0,'read>xy':0}):
    shift += timing['read>xy']
    if envelopename[1] == 1:
        envelope_pi = whichEnvelope(pi_len,*envelopename) * amp 
        envelope_half = whichEnvelope(pi_len,*envelopename) * 0.5 * amp 
    if envelopename[1] == 2:
        envelope_pi = whichEnvelope(pi_len,*envelopename) * amp 
        envelope_half = whichEnvelope(pi_len,envelopename[0],1) * amp 
    pulse1 = envelope_half << shift
    wavI1, wavQ1 = wn.mixing(pulse1,phase=2*np.pi*detune*t_run,freq=delta_ex,ratioIQ=-1.0,phaseDiff=phaseDiff,DRAGScaling=None)
    pulse3 = envelope_half << (t_run+(2*nwave+1)*pi_len+shift)
    wavI3, wavQ3 = wn.mixing(pulse3,phase=0,freq=delta_ex,ratioIQ=-1.0,phaseDiff=phaseDiff,DRAGScaling=None)

    if seqtype == 'CPMG':
        pulse2, step = wn.zero(), t_run / nwave
        for i in range(nwave):
            # pulse2 += ((envelope(during) << (during*0.5)+envelope(during) << (during*1.5)) << ((i+0.5)*step+(i+0.5)*2*during+shift))
            pulse2 += envelope_pi << ((i+0.5)*step+(i+0.5)*2*pi_len+shift)
        wavI2, wavQ2 = wn.mixing(pulse2,phase=np.pi/2,freq=delta_ex,ratioIQ=-1.0,phaseDiff=0.0,DRAGScaling=None)
    if seqtype == 'PDD':
        pulse2, step = wn.zero(), t_run / (nwave + 1)
        for i in range(nwave):
            # pulse2 += envelope(2*pi_len) << ((i+1)*step+(i+1)*2*pi_len+shift)
            # pulse2 += ((envelope(pi_len) << (pi_len*0.5)+envelope(pi_len) << (pi_len*1.5)) << ((i+0.5)*step+(i+0.5)*2*pi_len+shift))
            pulse2 += envelope_pi << ((i+1)*step+(i+0.5)*2*pi_len+shift)
        wavI2, wavQ2 = wn.mixing(pulse2,phase=np.pi/2,freq=delta_ex,ratioIQ=-1.0,phaseDiff=0.0,DRAGScaling=None)
    wavI, wavQ = wavI1 + wavI2 + wavI3, wavQ1 + wavQ2 + wavQ3
    
    return wavI, wavQ, wn.zero(), wn.zero()

async def Coherence_sequence(qubit,measure,kind,v_or_t,arg,**paras):
    awg= measure.awg[qubit.inst['ex_awg']]
    await awg.stop()
    for j,i in enumerate(tqdm(v_or_t,desc=''.join(('Coherence_',kind)))):
        paras[arg] = i
        name_ch = [measure.wave[kind][0][j],measure.wave[kind][1][j]]
        pulse = await funcarg(coherenceWave,qubit,**paras)
        await writeWave(awg,name_ch,pulse,mark=False)

################################################################################
# Z_cross波形
################################################################################

async def Z_cross_sequence(measure,kind_z,kind_ex,awg_z,awg_ex,v_rabi,halfpi):
    #t_range, sample_rate = measure.t_range, measure.sample_rate
    for j,i in enumerate(tqdm(v_rabi,desc='Z_cross_sequence')):
        name_ch = [measure.wave[kind_ex][0][j],measure.wave[kind_ex][1][j]]
        pulse_ex = await coherenceWave(measure.envelopename,300/1e9,halfpi/1e9,0,'PDD')
        await writeWave(awg_ex,name_ch,pulse_ex)
        pulse_z = (wn.square(200/1e9) << (50+halfpi+200)/1e9) * i
        await writeWave(awg_z,np.array(measure.wave[kind_z])[:,j],pulse_z)

################################################################################
# AC-Stark波形
################################################################################

async def ac_stark_wave(measure):
    awg = measure.awg['awgread']
    pulse_read = await modulation_read(measure,measure.delta,readlen=measure.readlen)
    width = 500e-9
    pulse = (wn.square(width) << (width/2+3000e-9)) * 1
    I, Q = wn.zero(), wn.zero()
    for i in measure.delta:
        wav_I, wav_Q = wn.mixing(pulse,phase=0.0,freq=i,ratioIQ=-1.0)
        I, Q = I + wav_I, Q + wav_Q
    pulse_acstark = (I,Q,wn.zero(),wn.zero())
    pulselist = np.array(pulse_read) + np.array(pulse_acstark)
    await writeWave(awg,['Readout_I','Readout_Q'],pulselist)
    
################################################################################
# ZPulse波形
################################################################################

async def zWave(volt=0.4,pi_len=500e-9,shift=1000e-9,offset=0,timing={'z>xy':0,'read>xy':0}):
    shift += timing['read>xy'] - timing['z>xy']
    pulse = (wn.square(pi_len) << (pi_len/2 + shift)) * volt + offset
    pulselist = (pulse,) 
    # await writeWave(awg,name,pulselist)
    return pulselist

################################################################################
# 偏置sequence
################################################################################

async def Z_sequence(qubit,measure,kind,v_or_t,arg,**paras):

    awg_z = measure.awg[qubit.inst['z_awg']]
    for j,i in enumerate(tqdm(v_or_t,desc='Z_sequence')):
        paras[arg] = i
        pulse_z = await funcarg(zWave,qubit,**paras)
        name_z = [measure.wave[kind][0][j]]
        await writeWave(awg_z,name_z,pulse_z)


################################################################################
# 单比特tomo波形
################################################################################

async def singleQgate(envelopename=['square',1],pi_len=30e-9,amp=1,shift=0,delta_ex=110e6,axis='X',\
    DRAGScaling=None,phaseDiff=0,timing={'z>xy':0,'read>xy':0}):
    
    shift += timing['read>xy']
    if envelopename[1] == 1:
        envelope_pi = whichEnvelope(pi_len,*envelopename) * amp 
        envelope_half = whichEnvelope(pi_len,*envelopename) * 0.5 * amp 
    if envelopename[1] == 2:
        envelope_pi = whichEnvelope(pi_len,*envelopename) * amp 
        envelope_half = whichEnvelope(pi_len,envelopename[0],1) * amp 

    if axis == 'X':
        phi = 0
        wav_I, wav_Q = wn.mixing(envelope_pi,phase=phi,freq=delta_ex,ratioIQ=-1.0,phaseDiff=phaseDiff,DRAGScaling=DRAGScaling)
    if axis == 'Xhalf':
        phi = 0
        wav_I, wav_Q = wn.mixing(envelope_half,phase=phi,freq=delta_ex,ratioIQ=-1.0,phaseDiff=phaseDiff,DRAGScaling=DRAGScaling)
    if axis == 'Xnhalf':
        phi = np.pi
        wav_I, wav_Q = wn.mixing(envelope_half,phase=phi,freq=delta_ex,ratioIQ=-1.0,phaseDiff=phaseDiff,DRAGScaling=DRAGScaling)
    if axis == 'Y':
        phi = np.pi/2
        wav_I, wav_Q = wn.mixing(envelope_pi,phase=phi,freq=delta_ex,ratioIQ=-1.0,phaseDiff=phaseDiff,DRAGScaling=DRAGScaling)
    if axis == 'Ynhalf':
        phi = -np.pi/2
        wav_I, wav_Q = wn.mixing(envelope_half,phase=phi,freq=delta_ex,ratioIQ=-1.0,phaseDiff=phaseDiff,DRAGScaling=DRAGScaling)
    if axis == 'Yhalf':
        phi = np.pi/2
        wav_I, wav_Q = wn.mixing(envelope_half,phase=phi,freq=delta_ex,ratioIQ=-1.0,phaseDiff=phaseDiff,DRAGScaling=DRAGScaling)
    if axis == 'Z':
        wav_I, wav_Q = wn.zero(), wn.zero()
    return wav_I, wav_Q, wn.zero(), wn.zero()

################################################################################
# 单比特tomo测试
################################################################################

async def tomoTest(measure,awg,t,halfpi,axis,name,DRAGScaling):
    gatepulse = await rabiWave(measure.envelopename,pi_len=t/1e9,shift=(halfpi)/1e9,\
        delta_ex=110e6,DRAGScaling=DRAGScaling)
    # gatepulse = await rabiWave(envelopename=measure.envelopename,pi_len=halfpi/1e9)
    tomopulse = await tomoWave(measure.envelopename,halfpi/1e9,\
        delta_ex=110e6,axis=axis,DRAGScaling=DRAGScaling)
    pulse = np.array(gatepulse) + np.array(tomopulse)
    await writeWave(awg,name,pulse)

################################################################################
# ramseyZpulse波形
################################################################################

async def ramseyZwave(measure,awg,halfpi,axis,name,DRAGScaling,shift):
    t_int = 100e-9
    gatepulse = await tomoWave(measure.envelopename,halfpi/1e9,shift=(t_int+(shift+halfpi)/1e9),\
        delta_ex=110e6,axis='Xhalf',DRAGScaling=DRAGScaling)
    # pulsespinecho = await rabiWave(measure.envelopename,pi_len=halfpi/1e9,shift=(t_int+halfpi/1e9),\
    #     phase=-np.pi/2,delta_ex=110e6,DRAGScaling=DRAGScaling)
    tomopulse = await tomoWave(measure.envelopename,halfpi/1e9,shift=shift/1e9,\
        delta_ex=110e6,axis=axis,DRAGScaling=DRAGScaling)
    pulse = np.array(gatepulse) + np.array(tomopulse)
    await writeWave(awg,name,pulse)

################################################################################
# ramseyZpulse_chen波形
################################################################################

async def ramseyZwave_chen(measure,awg,halfpi,axis,shift,name,DRAGScaling):
    t_int = 700e-9
    gatepulse = await tomoWave(measure.envelopename,halfpi/1e9,shift=(t_int+shift+halfpi/1e9),\
        delta_ex=110e6,axis='Xhalf',DRAGScaling=DRAGScaling)
    # pulsespinecho = await rabiWave(measure.envelopename,pi_len=halfpi/1e9,shift=(t_int+halfpi/1e9),\
    #     phase=-np.pi/2,delta_ex=110e6,DRAGScaling=DRAGScaling)
    tomopulse = await tomoWave(measure.envelopename,halfpi/1e9,delta_ex=110e6,axis=axis,DRAGScaling=DRAGScaling)
    pulse = np.array(gatepulse) + np.array(tomopulse)
    await writeWave(awg,name,pulse)

################################################################################
# AllXY drag detune
################################################################################

async def dragDetunewave(measure,awg,pilen,coef,axis,name_ch):
    pulse1 = await tomoWave(measure.envelopename,pi_len=pilen/1e9,delta_ex=110e6,axis=axis[0],DRAGScaling=coef)
    pulse2 = await tomoWave(measure.envelopename,pi_len=pilen/1e9,delta_ex=110e6,axis=axis[1],DRAGScaling=coef)
    pulse = np.array(pulse1) + np.array(pulse2)
    await writeWave(awg,name_ch,pulse)
    
################################################################################
# dragcoefHD
################################################################################

async def HDWave(measure,awg,pilen,coef,axis,nwave,name_ch):
    pulseequator2 = await tomoWave(measure.envelopename,pi_len=pilen/1e9,delta_ex=110e6,axis='Xhalf',DRAGScaling=coef,phaseDiff=0)
    pulsem, shift = np.array([wn.zero()]*4), 0
    for i in range(nwave):
        shift += pilen/1e9 +10e-9
        pulse1 = await tomoWave(measure.envelopename,pi_len=pilen/1e9,shift=shift,delta_ex=110e6,axis=axis[0],DRAGScaling=coef,phaseDiff=0)
        shift += pilen/1e9 + 10e-9
        pulse2 = await tomoWave(measure.envelopename,pi_len=pilen/1e9,shift=shift,delta_ex=110e6,axis=axis[1],DRAGScaling=coef,phaseDiff=0)
        pulsem += (np.array(pulse1)+np.array(pulse2))
    pulseequator1 = await tomoWave(measure.envelopename,pi_len=pilen/1e9,shift=(shift+pilen/1e9+10e-9),\
        delta_ex=110e6,axis='Xhalf',DRAGScaling=coef,phaseDiff=0)
    pulse = np.array(pulseequator1) + np.array(pulseequator2) + np.array(pulsem)
    await writeWave(awg,name_ch,pulse)

################################################################################
# RTO
################################################################################

async def rtoWave(measure,awg,pilen,name_ch):
    envelopename = measure.envelopename
    pulsegate = await tomoWave(envelopename,pi_len=pilen/1e9,delta_ex=110e6,axis='Xhalf',shift=(pilen+100)/1e9,DRAGScaling=None)
    pulsetomoy = await tomoWave(envelopename,pi_len=pilen/1e9,delta_ex=110e6,axis='Ynhalf',DRAGScaling=None)
    pulsetomox = await tomoWave(envelopename,pi_len=pilen/1e9,delta_ex=110e6,axis='Xhalf',DRAGScaling=None)
    pulse1 = np.array(pulsegate)+np.array(pulsetomoy)
    pulse2 = np.array(pulsegate)+np.array(pulsetomox)
    await writeWave(awg,name_ch[0],pulse1)
    await writeWave(awg,name_ch[1],pulse2)

################################################################################
# RB波形
################################################################################

async def rbWave(m,gate,envelopename=['square',1],pi_len=30e-9,amp=1,delta_ex=110e6,shift=0,\
    DRAGScaling=None,phaseDiff=0,timing={'z>xy':0,'read>xy':0}):

    op = mx.op

    mseq = mx.cliffordGroup_single(m,gate)
    if mseq == []:
        return
    rotseq = []
    for i in mseq[::-1]:
        rotseq += op[i]
    waveseq_I, waveseq_Q, wav = wn.zero(), wn.zero(), wn.zero()
    # rotseq = ['Xhalf','Xnhalf','Yhalf','Ynhalf']*m
    # if rotseq == []:
    #     return
    # print(rotseq)
    for i in rotseq:
        # paras = genParas(i)
        if i == 'I':
            waveseq_I += wn.zero()
            waveseq_Q += wn.zero()
            # continue
        else:
            wav_I, wav_Q, mrk1, mrk2 = await singleQgate(envelopename=envelopename,pi_len=pi_len,\
                amp=amp,shift=shift,delta_ex=delta_ex,axis=i,\
                DRAGScaling=DRAGScaling,phaseDiff=phaseDiff,timing=timing)
            waveseq_I += wav_I
            waveseq_Q += wav_Q
        if envelopename[1] == 2:
            if i in ['X','Y','Z']:
                shift += envelopename[1]*pi_len
            else:
                shift += pi_len
        if envelopename[1] == 1:
            shift += pi_len
        # if paras[1] == 'pi':
        #     shift += envelopename[1]*pi_len
        # if paras[1] == 'halfpi':
        #     shift += pi_len

    return waveseq_I, waveseq_Q, wn.zero(), wn.zero()
    
