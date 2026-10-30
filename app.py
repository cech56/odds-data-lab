import sqlite3,re,unicodedata
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd, requests
from bs4 import BeautifulSoup
import streamlit as st
from difflib import SequenceMatcher

st.set_page_config(page_title='Odds Data Lab',page_icon='⚽',layout='wide')
DB=Path(__file__).with_name('ODDS_DATA_LAB_V1.db'); IST=ZoneInfo('Europe/Istanbul')
LIVE='https://www.mackolik.com/perform/p0/ajax/components/competition/livescores/json?'
NESINE='https://www.nesine.com/iddaa/futbol'
PROGRAM_SOURCES=['https://arsiv.mackolik.com/Iddaa-Programi','https://arsiv2.mackolik.com/Iddaa-Programi']
HEAD={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36','Accept-Language':'tr-TR,tr;q=0.9'}
def db(): return sqlite3.connect(DB)
def norm(s):
 s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower(); return re.sub(r'[^a-z0-9]+',' ',s).strip()
def fnum(x):
 try:return float(str(x).replace(',','.'))
 except:return None
def init():
 with db() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS daily_matches(match_date TEXT,match_id TEXT,time_tr TEXT,match_name TEXT,home_team TEXT,away_team TEXT,competition_id TEXT,competition_name TEXT,state TEXT,status TEXT,ft_home TEXT,ft_away TEXT,ht_score TEXT,ms1 REAL,msx REAL,ms2 REAL,kg_var REAL,kg_yok REAL,gol25_alt REAL,gol25_ust REAL,iy_ms1 REAL,iy_msx REAL,iy_ms2 REAL,odds_source TEXT,updated_at TEXT,archived INTEGER DEFAULT 0,PRIMARY KEY(match_date,match_id))''')
  for col,typ in [('odds_source','TEXT'),('archived','INTEGER DEFAULT 0'),('iy05_alt','REAL'),('iy05_ust','REAL'),('iy15_alt','REAL'),('iy15_ust','REAL'),('odds_updated_at','TEXT')]:
   try:c.execute(f'ALTER TABLE daily_matches ADD COLUMN {col} {typ}')
   except:pass

def fetch_matches(day):
 ds=day.isoformat(); r=requests.get(LIVE,params={'sports[]':'Soccer','matchDate':ds},headers=HEAD,timeout=30);r.raise_for_status();d=(r.json().get('data') or {}); comps=d.get('competitions') or {}; rows=[]
 for mid,m in (d.get('matches') or {}).items():
  if not isinstance(m,dict):continue
  try:t=datetime.fromtimestamp(float(m.get('mstUtc'))/1000,ZoneInfo('UTC')).astimezone(IST).strftime('%H:%M')
  except:t=''
  cid=str(m.get('competitionId') or ''); co=comps.get(cid,{}) if isinstance(comps,dict) else {}; sc=m.get('score') or {}; ht=sc.get('ht')
  if isinstance(ht,dict):ht=f"{ht.get('home','')}-{ht.get('away','')}"
  rows.append((ds,str(m.get('id') or mid),t,m.get('matchName') or '',(m.get('homeTeam') or {}).get('name',''),(m.get('awayTeam') or {}).get('name',''),cid,co.get('name') or co.get('competitionName') or '',m.get('state') or '',m.get('status') or '',str(sc.get('home','')),str(sc.get('away','')),ht or '',datetime.now(IST).isoformat(timespec='seconds')))
 with db() as c:c.executemany('''INSERT INTO daily_matches(match_date,match_id,time_tr,match_name,home_team,away_team,competition_id,competition_name,state,status,ft_home,ft_away,ht_score,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(match_date,match_id) DO UPDATE SET time_tr=excluded.time_tr,match_name=excluded.match_name,home_team=excluded.home_team,away_team=excluded.away_team,competition_name=excluded.competition_name,state=excluded.state,status=excluded.status,ft_home=excluded.ft_home,ft_away=excluded.ft_away,ht_score=excluded.ht_score,updated_at=excluded.updated_at''',rows)
 return len(rows)

def compact(s):
 return re.sub(r'[^a-z0-9]+','',unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower())

def scrape_nesine(daily, day):
 """Nesine resmi bulten JSON'u. Yalnizca istenen gunun gercek, MS marketli futbol maclarini eslestirir."""
 try:
  api='https://cdnbulten.nesine.com/api/bulten/getprebultenfull'
  r=requests.get(api,headers={**HEAD,'Accept':'application/json,text/plain,*/*','Referer':'https://www.nesine.com/'},timeout=40); r.raise_for_status(); data=r.json()
  nesine_day=day.strftime('%d.%m.%Y'); parsed=[]
  for e in (data.get('sg',{}).get('EA') or []):
   if e.get('TYPE')!=1 or e.get('GT')!=1 or not e.get('HN') or not e.get('AN') or e.get('D')!=nesine_day:continue
   markets=e.get('MA',[]) or []
   if not any(mk.get('MTID')==1 for mk in markets):continue
   o={'home':e.get('HN',''),'away':e.get('AN',''),'time':str(e.get('T') or '')[:5],'ms1':None,'msx':None,'ms2':None,'gol25_alt':None,'gol25_ust':None,'kg_var':None,'kg_yok':None,'iy05_alt':None,'iy05_ust':None,'iy15_alt':None,'iy15_ust':None}
   for mk in markets:
    vals={x.get('N'):fnum(x.get('O')) for x in (mk.get('OCA') or [])}; mtid=mk.get('MTID')
    try:sov=float(mk.get('SOV') or 0)
    except:sov=0
    if mtid==1:o['ms1'],o['msx'],o['ms2']=vals.get(1),vals.get(2),vals.get(3)
    elif mtid==12 and abs(sov-2.5)<.001:o['gol25_alt'],o['gol25_ust']=vals.get(1),vals.get(2)
    elif mtid==38:o['kg_var'],o['kg_yok']=vals.get(1),vals.get(2)
    elif mtid==256 and abs(sov-.5)<.001:o['iy05_alt'],o['iy05_ust']=vals.get(1),vals.get(2)
    elif mtid==20 and abs(sov-1.5)<.001:o['iy15_alt'],o['iy15_ust']=vals.get(1),vals.get(2)
   if all(o[k] is not None for k in ('ms1','msx','ms2')):parsed.append(o)
  out=[]; used=set()
  for _,m in daily.iterrows():
   h,a=norm(m.home_team),norm(m.away_team); best=None; bs=0
   for i,o in enumerate(parsed):
    if i in used:continue
    sc=(SequenceMatcher(None,h,norm(o['home'])).ratio()+SequenceMatcher(None,a,norm(o['away'])).ratio())/2
    if m.time_tr and o['time']==m.time_tr:sc+=.08
    if sc>bs:bs=sc;best=(i,o)
   if best and bs>=.78:
    i,o=best;used.add(i);out.append({'match_id':m.match_id,**{k:o[k] for k in ('ms1','msx','ms2','gol25_alt','gol25_ust','kg_var','kg_yok','iy05_alt','iy05_ust','iy15_alt','iy15_ust')},'source':'Nesine Bulten API'})
  return out,f'Nesine API {nesine_day}: {len(parsed)} gercek mac / {len(out)} eslesme'
 except Exception as e:return [],f'Nesine API hata: {e}'

def scrape_program():
 # Legacy public program page: MS 1-X-2 + 2.5 Alt/Üst + double chance are visible without opening match detail.
 last=''
 for url in PROGRAM_SOURCES:
  try:
   r=requests.get(url,headers=HEAD,timeout=25); last=f'{url}: HTTP {r.status_code}'
   if r.status_code!=200 or len(r.text)<1000:continue
   soup=BeautifulSoup(r.text,'html.parser'); out=[]
   for tr in soup.find_all('tr'):
    cells=[' '.join(x.stripped_strings) for x in tr.find_all(['td','th'])]
    if not cells:continue
    joined=' | '.join(cells); tm=next((x for x in cells if re.fullmatch(r'\d{1,2}:\d{2}',x)),None)
    if not tm:continue
    # Find likely team-v-team text and decimal odds. Program table order is MS1, X, MS2, 2.5 Alt, Üst, then DC.
    name=next((x for x in cells if (' - ' in x or ' vs ' in x.lower()) and len(x)>5),None)
    nums=[]
    for x in cells:
     if re.fullmatch(r'\d+[\.,]\d{2}',x.strip()):
      v=fnum(x)
      if v and 1.01<=v<=100:nums.append(v)
    if name and len(nums)>=3:out.append({'time':tm,'name':name,'ms1':nums[0],'msx':nums[1],'ms2':nums[2],'gol25_alt':nums[3] if len(nums)>4 else None,'gol25_ust':nums[4] if len(nums)>4 else None,'source':url})
   if out:return out,last
  except Exception as e:last=f'{url}: {e}'
 return [],last

def attach_odds(day):
 daily=load_daily(day.isoformat())
 if daily.empty:return 0,'Önce maçları çek.'
 # Her yenilemede eski oranlari temizle. Boylece sabahki oranlar oglen yeni veri gelmezse
 # yanlislikla "guncel" diye ekranda kalmaz.
 with db() as c:
  c.execute('''UPDATE daily_matches SET
   ms1=NULL,msx=NULL,ms2=NULL,kg_var=NULL,kg_yok=NULL,
   gol25_alt=NULL,gol25_ust=NULL,iy_ms1=NULL,iy_msx=NULL,iy_ms2=NULL,
   iy05_alt=NULL,iy05_ust=NULL,iy15_alt=NULL,iy15_ust=NULL,
   odds_source=NULL,odds_updated_at=NULL
   WHERE match_date=?''',[day.isoformat()])
 daily=load_daily(day.isoformat())
 total=0; notes=[]
 # 1) NESINE is primary and is requested again on every button press.
 nes, msg=scrape_nesine(daily,day);notes.append(msg)
 with db() as c:
  for o in nes:
   c.execute('UPDATE daily_matches SET ms1=?,msx=?,ms2=?,gol25_alt=?,gol25_ust=?,kg_var=?,kg_yok=?,iy05_alt=?,iy05_ust=?,iy15_alt=?,iy15_ust=?,odds_source=?,updated_at=?,odds_updated_at=? WHERE match_date=? AND match_id=?',
     (o['ms1'],o['msx'],o['ms2'],o['gol25_alt'],o['gol25_ust'],o['kg_var'],o['kg_yok'],o['iy05_alt'],o['iy05_ust'],o['iy15_alt'],o['iy15_ust'],o['source'],datetime.now(IST).isoformat(timespec='seconds'),datetime.now(IST).isoformat(timespec='seconds'),day.isoformat(),o['match_id']))
   total+=1
 # 2) Mackolik archive is fallback only for still-empty matches.
 daily=load_daily(day.isoformat()); missing=daily[daily[['ms1','msx','ms2']].isna().any(axis=1)]
 odds,msg2=scrape_program();notes.append(msg2)
 if odds and not missing.empty:
  with db() as c:
   for _,m in missing.iterrows():
    best=None;bs=0;a=norm(m.match_name)
    for o in odds:
     s=SequenceMatcher(None,a,norm(o['name'])).ratio()
     if m.time_tr and o['time']==m.time_tr:s+=.08
     if s>bs:bs=s;best=o
    if best and bs>=.72:
     c.execute('UPDATE daily_matches SET ms1=?,msx=?,ms2=?,gol25_alt=?,gol25_ust=?,odds_source=?,updated_at=?,odds_updated_at=? WHERE match_date=? AND match_id=?',
      (best['ms1'],best['msx'],best['ms2'],best['gol25_alt'],best['gol25_ust'],best['source'],datetime.now(IST).isoformat(timespec='seconds'),datetime.now(IST).isoformat(timespec='seconds'),day.isoformat(),m.match_id));total+=1
 return total,' | '.join(notes)

def load_daily(ds):
 with db() as c:return pd.read_sql_query('SELECT * FROM daily_matches WHERE match_date=? ORDER BY time_tr,match_name',c,params=[ds])
@st.cache_data(show_spinner=False)
def archive():
 with db() as c:return pd.read_sql_query('SELECT id,date_iso,Tarih,Saat,Maç,"İY Skor","Maç Sonu",ms1,msx,ms2,kg_var,kg_yok,gol25_alt,gol25_ust,iy_ms1,iy_msx,iy_ms2 FROM matches',c)
def score(s):
 m=re.search(r'(\d+)\s*[-:]\s*(\d+)',str(s or ''));return (int(m.group(1)),int(m.group(2))) if m else None
def prepared(d):
 d=d.copy();ft=d['Maç Sonu'].map(score);ht=d['İY Skor'].map(score)
 for n,f in {'MS 1':lambda x:x[0]>x[1],'MS X':lambda x:x[0]==x[1],'MS 2':lambda x:x[0]<x[1],'2.5 ÜST':lambda x:sum(x)>2,'2.5 ALT':lambda x:sum(x)<3,'KG VAR':lambda x:x[0]>0 and x[1]>0,'KG YOK':lambda x:not(x[0]>0 and x[1]>0)}.items():d[n]=ft.map(lambda x:int(bool(x) and f(x)))
 for n,f in {'İY 0.5 ÜST':lambda x:sum(x)>0,'İY 0.5 ALT':lambda x:sum(x)==0,'İY 1.5 ÜST':lambda x:sum(x)>1,'İY 1.5 ALT':lambda x:sum(x)<2}.items():d[n]=ht.map(lambda x:int(bool(x) and f(x)))
 d['_ft']=ft.notna();d['_ht']=ht.notna();return d

def archive_finished(day):
 ds=day.isoformat(); n=0
 with db() as c:
  rows=c.execute('SELECT match_id,time_tr,match_name,ht_score,ft_home,ft_away,ms1,msx,ms2,kg_var,kg_yok,gol25_alt,gol25_ust,iy_ms1,iy_msx,iy_ms2,iy05_alt,iy05_ust,iy15_alt,iy15_ust FROM daily_matches WHERE match_date=? AND state="post" AND archived=0 AND ms1 IS NOT NULL AND msx IS NOT NULL AND ms2 IS NOT NULL',[ds]).fetchall()
  for r in rows:
   mid,tm,name,ht,fh,fa,*o=r
   if not(str(fh).isdigit() and str(fa).isdigit() and score(ht)):continue
   vals={'Tarih':day.strftime('%d-%m-%Y'),'Saat':tm,'Maç':name,'İY Skor':ht,'Maç Sonu':f'{fh}-{fa}','MS 1':o[0],'MS X':o[1],'MS 2':o[2],'KG Var':o[3],'KG Yok':o[4],'Gol 2,5 Alt':o[5],'Gol 2,5 Üst':o[6],'İY MS 1':o[7],'İY MS X':o[8],'İY MS 2':o[9],'İY Gol 0,5 Alt':o[10],'İY Gol 0,5 Üst':o[11],'İY Gol 1,5 Alt':o[12],'İY Gol 1,5 Üst':o[13]}
   cols=list(vals)+['date_iso','ms1','msx','ms2','kg_var','kg_yok','gol25_alt','gol25_ust','iy_ms1','iy_msx','iy_ms2']; vv=list(vals.values())+[ds]+o[:10]
   c.execute('INSERT INTO matches('+','.join('"'+x+'"' for x in cols)+') VALUES('+','.join('?'*len(cols))+')',vv);c.execute('UPDATE daily_matches SET archived=1 WHERE match_date=? AND match_id=?',[ds,mid]);n+=1
 return n


def find_similar_matches(current, historical, reference='ms1'):
    """Secilen MS oraninda toleransli, 2.5 UST oraninda birebir eslesen maclari bulur."""
    tolerances=[.05,.07,.10,.15,.20,.25,.30,.40,.50,1.00]
    empty=historical.iloc[0:0].copy()
    if pd.isna(current.get(reference)) or pd.isna(current.get('gol25_ust')):
        return empty, None

    same_over=(historical.gol25_ust.notna()
               &historical.gol25_ust.round(2).eq(round(float(current.gol25_ust),2)))
    valid=same_over & historical[reference].notna()

    s=empty
    tol=None
    for current_tol in tolerances:
        m=valid & (historical[reference]-float(current[reference])).abs().le(current_tol)
        s=historical[m]
        tol=current_tol
        if len(s)>=5:
            break
    return s,tol


def strong_analyses(ready, historical, threshold=75.0):
    """MS1 ve MS2 ayri arastirilir; yalnizca ikisi de 2.5 UST'i desteklerse listelenir."""
    results=[]
    for _,r in ready.iterrows():
        if pd.isna(r.get('ms1')) or pd.isna(r.get('ms2')) or pd.isna(r.get('gol25_ust')):
            continue

        sample1,tol1=find_similar_matches(r,historical,'ms1')
        sample2,tol2=find_similar_matches(r,historical,'ms2')

        # Her iki arastirmada da en az 5 tamamlanmis mac olmali.
        ft1=sample1[sample1._ft] if not sample1.empty else sample1
        ft2=sample2[sample2._ft] if not sample2.empty else sample2
        n1,n2=len(ft1),len(ft2)
        if n1<5 or n2<5:
            continue

        hits1=int(ft1['2.5 ÜST'].sum())
        hits2=int(ft2['2.5 ÜST'].sum())
        pct1=round(100*hits1/n1,1)
        pct2=round(100*hits2/n2,1)

        # Iki bagimsiz arastirma da ayni secenegi %75+ desteklemeli.
        if pct1>=threshold and pct2>=threshold:
            results.append({
                'Saat':r.time_tr,
                'Maç':r.match_name,
                'Lig':r.competition_name,
                'Seçenek':'2.5 ÜST',
                'MS1 Araştırması %':pct1,
                'MS1 Başarılı/Örnek':f'{hits1}/{n1}',
                'MS1 Tolerans':f'±{tol1:.2f}',
                'MS2 Araştırması %':pct2,
                'MS2 Başarılı/Örnek':f'{hits2}/{n2}',
                'MS2 Tolerans':f'±{tol2:.2f}',
                'MS1':r.ms1,
                'MS2':r.ms2,
                '2.5 ÜST':r.gol25_ust
            })

    columns=['Saat','Maç','Lig','Seçenek','MS1 Araştırması %',
             'MS1 Başarılı/Örnek','MS1 Tolerans','MS2 Araştırması %',
             'MS2 Başarılı/Örnek','MS2 Tolerans','MS1','MS2','2.5 ÜST']
    if not results:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(results).sort_values(
        ['MS1 Araştırması %','MS2 Araştırması %','Saat'],
        ascending=[False,False,True]
    ).reset_index(drop=True)

init(); DF=prepared(archive()); today=datetime.now(IST).date(); ds=today.isoformat()
st.title('ODDS DATA LAB');st.caption(f'{len(DF):,} geçmiş maç • Otomatik günlük maç + doğrulanmış oran + sonuç arşivleme')
t1,t2,t3,t4=st.tabs(['⚽ BUGÜNÜN MAÇLARI','🔥 GÜÇLÜ ANALİZLER','📊 ANALİZ','🔎 ARŞİV'])
with t1:
 st.subheader(today.strftime('%d.%m.%Y'))
 c1,c2,c3=st.columns(3)
 if c1.button('1 · MAÇLARI + GÜNCEL ORANLARI ÇEK',use_container_width=True):
  try:
   nm=fetch_matches(today)
   no,msg=attach_odds(today)
   st.success(f'{nm} maç güncellendi • {no} güncel oran eşleşmesi işlendi • {msg}')
   st.rerun()
  except Exception as e:st.error(str(e))
 if c2.button('2 · ORANLARI ŞİMDİ YENİLE',use_container_width=True):
  n,msg=attach_odds(today)
  st.success(f'{n} güncel oran eşleşmesi işlendi • {msg}') if n else st.warning('Oran kaynağı bu çalıştırmada veri vermedi. Eski oranlar güncel diye gösterilmedi. '+msg)
  st.rerun()
 if c3.button('3 · SONUÇLARI ARŞİVLE',use_container_width=True):
  try:fetch_matches(today)
  except:pass
  n=archive_finished(today);st.cache_data.clear();st.success(f'{n} bitmiş maç ana arşive eklendi');st.rerun()
 d=load_daily(ds)
 if d.empty:st.info('Önce MAÇLARI ÇEK.')
 else:
  a=int(d[['ms1','msx','ms2']].notna().all(axis=1).sum()); n_nesine=int(d.odds_source.fillna('').str.contains('Nesine',case=False).sum()); n_macko=int(d.odds_source.fillna('').str.contains('mackolik.com',case=False).sum())
  cA,cB,cC,cD=st.columns(4);cA.metric('Günün maçları',len(d));cB.metric('Analize hazır',a);cC.metric('Nesine',n_nesine);cD.metric('Yedek kaynak',n_macko)
  if 'odds_updated_at' in d.columns and d.odds_updated_at.notna().any():
   try:
    last=pd.to_datetime(d.odds_updated_at.dropna()).max()
    st.success(f'🟢 Oranlar son yenilendi: {last.strftime("%H:%M:%S")} • Butona her basışta kaynaklardan yeniden çekilir.')
   except:pass
  q=st.text_input('🔎 Maç ara'); sh=d if not q else d[d.match_name.str.contains(q,case=False,na=False,regex=False)]
  table_cols=['time_tr','match_name','competition_name','state','ms1','msx','ms2','gol25_alt','gol25_ust','kg_var','kg_yok','iy05_alt','iy05_ust','iy15_alt','iy15_ust','odds_source','odds_updated_at']
  for col in table_cols:
   if col not in sh.columns: sh[col]=None
  st.dataframe(sh[table_cols],use_container_width=True,hide_index=True)
with t2:
 d=load_daily(ds)
 if not d.empty:
  for col in ['iy05_alt','iy05_ust','iy15_alt','iy15_ust','odds_updated_at']:
   if col not in d.columns:d[col]=None
  ready=d[d[['ms1','gol25_ust']].notna().all(axis=1)]
 else:ready=d
 st.subheader('🔥 GÜNÜN GÜÇLÜ ANALİZLERİ')
 st.caption('İki bağımsız araştırma yapılır: MS 1 toleranslı + birebir 2.5 ÜST ve MS 2 toleranslı + birebir 2.5 ÜST. Her iki araştırmada da en az 5 geçmiş maç ve %75+ 2.5 ÜST başarısı şarttır.')
 if ready.empty:
  st.warning('Henüz taranacak doğrulanmış güncel oran yok. Önce BUGÜNÜN MAÇLARI sekmesinden maçları ve oranları çek.')
 else:
  with st.spinner(f'{len(ready)} maç otomatik taranıyor...'):
   strong=strong_analyses(ready,DF,75.0)
  unique_matches=strong['Maç'].nunique() if not strong.empty else 0
  c1,c2,c3=st.columns(3)
  c1.metric('Taranan maç',len(ready))
  c2.metric('%75+ bulunan maç',unique_matches)
  c3.metric('Güçlü seçenek',len(strong))
  if strong.empty:
   st.info('Bugün %75 ve üzeri tarihsel başarı gösteren seçenek bulunamadı.')
  else:
   st.success(f'🔥 {unique_matches} maçta toplam {len(strong)} adet %75+ seçenek bulundu.')
   st.dataframe(strong,use_container_width=True,hide_index=True)
   st.caption('Listeye yalnızca MS 1 araştırması ve MS 2 araştırması ayrı ayrı %75+ 2.5 ÜST sonucu verdiğinde maç eklenir. Her iki araştırmada 2.5 ÜST oranı birebir eşleştirilir; yalnızca MS oranında tolerans uygulanır. Tarihsel sonuçlar garanti değildir.')

with t3:
 d=load_daily(ds)
 if not d.empty:
  for col in ['iy05_alt','iy05_ust','iy15_alt','iy15_ust','odds_updated_at']:
   if col not in d.columns: d[col]=None
  ready=d[d[['ms1','gol25_ust']].notna().all(axis=1)]
 else: ready=d
 if ready.empty:st.warning('Henüz analiz edilecek doğrulanmış MS oranı yok.')
 else:
  labels=[f'{r.time_tr} • {r.match_name}' for _,r in ready.iterrows()];pick=st.selectbox('Maç seç',labels);r=ready.iloc[labels.index(pick)]
  st.markdown(f"### {r.match_name}");st.write(f"MS: **{r.ms1:.2f} / {r.msx:.2f} / {r.ms2:.2f}**")
  if 'odds_updated_at' in ready.columns and pd.notna(r.odds_updated_at):
   try:st.caption(f"🟢 Bu maçın oranları: {pd.to_datetime(r.odds_updated_at).strftime('%H:%M:%S')} tarihinde/saatinde yenilendi")
   except:pass
  codd1,codd2,codd3=st.columns(3)
  codd1.write(f"**2.5 Gol**  ALT: {r.gol25_alt if pd.notna(r.gol25_alt) else '-'}  •  ÜST: {r.gol25_ust if pd.notna(r.gol25_ust) else '-'}")
  codd2.write(f"**İY 0.5**  ALT: {r.iy05_alt if pd.notna(r.iy05_alt) else '-'}  •  ÜST: {r.iy05_ust if pd.notna(r.iy05_ust) else '-'}")
  codd3.write(f"**İY 1.5**  ALT: {r.iy15_alt if pd.notna(r.iy15_alt) else '-'}  •  ÜST: {r.iy15_ust if pd.notna(r.iy15_ust) else '-'}")
  # Benzer maç filtresi: MS 1 kademeli toleranslı, 2.5 ÜST birebir aynı.
  if pd.isna(r.gol25_ust):
   st.warning('Bu maçta 2.5 ÜST oranı bulunmadığı için analiz yapılamıyor.')
  else:
   s,tol=find_similar_matches(r,DF)
   ctol1,ctol2=st.columns(2)
   ctol1.metric('Benzer geçmiş maç',len(s))
   ctol2.metric('MS 1 toleransı',f'±{tol:.2f}' if tol is not None else '-')
   st.caption(f"2.5 ÜST eşleşmesi: birebir {r.gol25_ust:.2f} (tolerans yok)")
   if len(s)<5:
    st.warning('MS 1 toleransı en yüksek seviyeye çıkarıldı ancak aynı 2.5 ÜST oranıyla en az 5 geçmiş maç bulunamadı.')
   else:
    rr=[]
    for n,base in [(x,s[s._ft]) for x in ['MS 1','MS X','MS 2','2.5 ÜST','2.5 ALT','KG VAR','KG YOK']]+[(x,s[s._ht]) for x in ['İY 0.5 ÜST','İY 0.5 ALT','İY 1.5 ÜST','İY 1.5 ALT']]:
     N=len(base);h=int(base[n].sum()) if N else 0;rr.append([n,h,N,round(100*h/N,1) if N else None])
    st.dataframe(pd.DataFrame(rr,columns=['İstatistik','Başarılı','Örnek','Yüzde %']).sort_values('Yüzde %',ascending=False),use_container_width=True,hide_index=True)
    st.dataframe(s[['date_iso','Saat','Maç','İY Skor','Maç Sonu','ms1','gol25_ust']].sort_values(['date_iso','Saat'],ascending=False).head(100),use_container_width=True,hide_index=True)
with t4:
 q=st.text_input('Takım / maç ara',key='arc');
 if q:st.dataframe(DF[DF.Maç.str.contains(q,case=False,na=False,regex=False)][['date_iso','Saat','Maç','İY Skor','Maç Sonu','ms1','msx','ms2']].sort_values(['date_iso','Saat'],ascending=False).head(200),use_container_width=True,hide_index=True)
                                                                               
