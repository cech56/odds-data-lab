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
  for col,typ in [('odds_source','TEXT'),('archived','INTEGER DEFAULT 0')]:
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
   o={'home':e.get('HN',''),'away':e.get('AN',''),'time':str(e.get('T') or '')[:5],'ms1':None,'msx':None,'ms2':None,'gol25_alt':None,'gol25_ust':None,'kg_var':None,'kg_yok':None}
   for mk in markets:
    vals={x.get('N'):fnum(x.get('O')) for x in (mk.get('OCA') or [])}; mtid=mk.get('MTID')
    try:sov=float(mk.get('SOV') or 0)
    except:sov=0
    if mtid==1:o['ms1'],o['msx'],o['ms2']=vals.get(1),vals.get(2),vals.get(3)
    elif mtid==12 and abs(sov-2.5)<.001:o['gol25_alt'],o['gol25_ust']=vals.get(1),vals.get(2)
    elif mtid==38:o['kg_var'],o['kg_yok']=vals.get(1),vals.get(2)
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
    i,o=best;used.add(i);out.append({'match_id':m.match_id,**{k:o[k] for k in ('ms1','msx','ms2','gol25_alt','gol25_ust','kg_var','kg_yok')},'source':'Nesine Bulten API'})
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
 total=0; notes=[]
 # 1) NESINE is primary.
 nes, msg=scrape_nesine(daily,day);notes.append(msg)
 with db() as c:
  for o in nes:
   c.execute('UPDATE daily_matches SET ms1=?,msx=?,ms2=?,gol25_alt=?,gol25_ust=?,kg_var=?,kg_yok=?,odds_source=?,updated_at=? WHERE match_date=? AND match_id=?',
     (o['ms1'],o['msx'],o['ms2'],o['gol25_alt'],o['gol25_ust'],o['kg_var'],o['kg_yok'],o['source'],datetime.now(IST).isoformat(timespec='seconds'),day.isoformat(),o['match_id']))
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
     c.execute('UPDATE daily_matches SET ms1=?,msx=?,ms2=?,gol25_alt=?,gol25_ust=?,odds_source=?,updated_at=? WHERE match_date=? AND match_id=?',
      (best['ms1'],best['msx'],best['ms2'],best['gol25_alt'],best['gol25_ust'],best['source'],datetime.now(IST).isoformat(timespec='seconds'),day.isoformat(),m.match_id));total+=1
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
  rows=c.execute('SELECT match_id,time_tr,match_name,ht_score,ft_home,ft_away,ms1,msx,ms2,kg_var,kg_yok,gol25_alt,gol25_ust,iy_ms1,iy_msx,iy_ms2 FROM daily_matches WHERE match_date=? AND state="post" AND archived=0 AND ms1 IS NOT NULL AND msx IS NOT NULL AND ms2 IS NOT NULL',[ds]).fetchall()
  for r in rows:
   mid,tm,name,ht,fh,fa,*o=r
   if not(str(fh).isdigit() and str(fa).isdigit() and score(ht)):continue
   vals={'Tarih':day.strftime('%d-%m-%Y'),'Saat':tm,'Maç':name,'İY Skor':ht,'Maç Sonu':f'{fh}-{fa}','MS 1':o[0],'MS X':o[1],'MS 2':o[2],'KG Var':o[3],'KG Yok':o[4],'Gol 2,5 Alt':o[5],'Gol 2,5 Üst':o[6],'İY MS 1':o[7],'İY MS X':o[8],'İY MS 2':o[9]}
   cols=list(vals)+['date_iso','ms1','msx','ms2','kg_var','kg_yok','gol25_alt','gol25_ust','iy_ms1','iy_msx','iy_ms2']; vv=list(vals.values())+[ds]+o
   c.execute('INSERT INTO matches('+','.join('"'+x+'"' for x in cols)+') VALUES('+','.join('?'*len(cols))+')',vv);c.execute('UPDATE daily_matches SET archived=1 WHERE match_date=? AND match_id=?',[ds,mid]);n+=1
 return n

init(); DF=prepared(archive()); today=datetime.now(IST).date(); ds=today.isoformat()
st.title('ODDS DATA LAB');st.caption(f'{len(DF):,} geçmiş maç • Otomatik günlük maç + doğrulanmış oran + sonuç arşivleme')
t1,t2,t3=st.tabs(['⚽ BUGÜNÜN MAÇLARI','📊 ANALİZ','🔎 ARŞİV'])
with t1:
 st.subheader(today.strftime('%d.%m.%Y'))
 c1,c2,c3=st.columns(3)
 if c1.button('1 · MAÇLARI ÇEK',use_container_width=True):
  try:st.success(f'{fetch_matches(today)} maç güncellendi');st.rerun()
  except Exception as e:st.error(str(e))
 if c2.button('2 · NESİNE + YEDEK ORANLARI BAĞLA',use_container_width=True):
  n,msg=attach_odds(today);st.success(f'{n} oran eşleşmesi işlendi • {msg}') if n else st.warning('Oran kaynağı bu çalıştırmada veri vermedi. '+msg);st.rerun()
 if c3.button('3 · SONUÇLARI ARŞİVLE',use_container_width=True):
  try:fetch_matches(today)
  except:pass
  n=archive_finished(today);st.cache_data.clear();st.success(f'{n} bitmiş maç ana arşive eklendi');st.rerun()
 d=load_daily(ds)
 if d.empty:st.info('Önce MAÇLARI ÇEK.')
 else:
  a=int(d[['ms1','msx','ms2']].notna().all(axis=1).sum()); n_nesine=int(d.odds_source.fillna('').str.contains('Nesine',case=False).sum()); n_macko=int(d.odds_source.fillna('').str.contains('mackolik.com',case=False).sum())
  cA,cB,cC,cD=st.columns(4);cA.metric('Günün maçları',len(d));cB.metric('Analize hazır',a);cC.metric('Nesine',n_nesine);cD.metric('Yedek kaynak',n_macko)
  q=st.text_input('🔎 Maç ara'); sh=d if not q else d[d.match_name.str.contains(q,case=False,na=False,regex=False)]
  st.dataframe(sh[['time_tr','match_name','competition_name','state','ms1','msx','ms2','gol25_alt','gol25_ust','kg_var','kg_yok','odds_source']],use_container_width=True,hide_index=True)
with t2:
 d=load_daily(ds); ready=d[d[['ms1','msx','ms2']].notna().all(axis=1)] if not d.empty else d
 if ready.empty:st.warning('Henüz analiz edilecek doğrulanmış MS oranı yok.')
 else:
  labels=[f'{r.time_tr} • {r.match_name}' for _,r in ready.iterrows()];pick=st.selectbox('Maç seç',labels);r=ready.iloc[labels.index(pick)]
  st.markdown(f"### {r.match_name}");st.write(f"MS: **{r.ms1:.2f} / {r.msx:.2f} / {r.ms2:.2f}**")
  # Kademeli tolerans: ±0.05'ten başla; en az 10 benzer maç bulunana kadar genişlet.
  # Bir adımda 10'u aşarsa o adımda bulunan tüm maçları kullan.
  tolerances=[.05,.07,.10,.15,.20,.25,.30,.40,.50,1.00]
  s=DF.iloc[0:0].copy();tol=tolerances[-1]
  valid=DF.ms1.notna()&DF.msx.notna()&DF.ms2.notna()
  for current_tol in tolerances:
   m=valid&(DF.ms1-r.ms1).abs().le(current_tol)&(DF.msx-r.msx).abs().le(current_tol)&(DF.ms2-r.ms2).abs().le(current_tol)
   s=DF[m];tol=current_tol
   if len(s)>=10:break
  ctol1,ctol2=st.columns(2)
  ctol1.metric('Benzer geçmiş maç',len(s))
  ctol2.metric('Kullanılan tolerans',f'±{tol:.2f}')
  rr=[]
  for n,base in [(x,s[s._ft]) for x in ['MS 1','MS X','MS 2','2.5 ÜST','2.5 ALT','KG VAR','KG YOK']]+[(x,s[s._ht]) for x in ['İY 0.5 ÜST','İY 0.5 ALT','İY 1.5 ÜST','İY 1.5 ALT']]:
   N=len(base);h=int(base[n].sum()) if N else 0;rr.append([n,h,N,round(100*h/N,1) if N else None])
  st.dataframe(pd.DataFrame(rr,columns=['İstatistik','Başarılı','Örnek','Yüzde %']).sort_values('Yüzde %',ascending=False),use_container_width=True,hide_index=True)
  st.dataframe(s[['date_iso','Saat','Maç','İY Skor','Maç Sonu','ms1','msx','ms2']].sort_values(['date_iso','Saat'],ascending=False).head(100),use_container_width=True,hide_index=True)
with t3:
 q=st.text_input('Takım / maç ara',key='arc');
 if q:st.dataframe(DF[DF.Maç.str.contains(q,case=False,na=False,regex=False)][['date_iso','Saat','Maç','İY Skor','Maç Sonu','ms1','msx','ms2']].sort_values(['date_iso','Saat'],ascending=False).head(200),use_container_width=True,hide_index=True)
