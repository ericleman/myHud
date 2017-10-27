'''
cash_table_session_summary indique:
- les tables: id_table
- les joueurs: id_player
- leurs positions: seat
On peut considérer qu'une table est toujours active quand date_end est à moins de 5 minutes (attention au fuseau horaire)
Ensuite dans cash_table, on récupère le nom table_name en liant avec id_table
Dans la table player, on récupère les noms player_name grâce à id_player.
'''
import psycopg2
import psycopg2.extras
from subprocess import getoutput
from tkinter import ttk
from time import sleep
import tkinter as tk

DB="dbname='PT4' user='postgres' host='localhost' password='a'"
SQL_GET_PLAYER = """SELECT player.player_name,cash_table.table_name,seat,
                      (select seat from cash_table_session_summary C 
                      where C.id_table=X.id_table and (C.date_end + interval '3 minutes') > (now() at time zone 'UTC')
                      and C.id_player=(select id_player from player where player_name='CookandPoker')) as myseat  
          FROM (SELECT id_table,id_player,seat,row_number() over(partition by seat,id_table order by date_end desc) as rn
              FROM cash_table_session_summary where (date_end + interval '3 minutes') > (now() at time zone 'UTC')) X,
          cash_table, player
          where cash_table.id_table = X.id_table
          AND player.id_player = X.id_player
          and X.rn = 1
          and (select seat from cash_table_session_summary C 
                      where C.id_table=X.id_table and (C.date_end + interval '3 minutes') > (now() at time zone 'UTC')
                      and C.id_player=(select id_player from player where player_name='CookandPoker')) is not null"""
SQL_GET_STATS = """SELECT sum(case when S.flg_vpip then 1 else 0 end) as cnt_vpip,
          sum(case when S.id_hand > 0 then 1 else 0 end) as cnt_hands,
          sum(case when LAP.action = '' then 1 else 0 end) as cnt_walks,
          sum(case when S.cnt_p_raise > 0 then 1 else 0 end) as cnt_pfr,
          sum(case when LAP.action LIKE '__%' OR (LAP.action LIKE '_' AND (S.amt_before > (CL.amt_bb + S.amt_ante)) AND (S.amt_p_raise_facing < (S.amt_before - (S.amt_blind + S.amt_ante))) AND (S.flg_p_open_opp OR S.cnt_p_face_limpers > 0 OR S.flg_p_3bet_opp OR S.flg_p_4bet_opp) ) then 1 else 0 end) as cnt_pfr_opp,
          sum(case when S.flg_p_3bet then 1 else 0 end) as cnt_p_3bet,
          sum(case when S.flg_p_3bet_opp then 1 else 0 end) as cnt_p_3bet_opp,
          sum(case when S.flg_f_cbet then 1 else 0 end) as cnt_f_cbet,
          sum(case when S.flg_f_cbet_opp then 1 else 0 end) as cnt_f_cbet_opp,
          sum(case when S.enum_f_cbet_action = 'F' then 1 else 0 end) as cnt_f_cbet_def_action_fold,
          sum(case when S.flg_f_cbet_def_opp then 1 else 0 end) as cnt_f_cbet_def_opp
          from cash_hand_player_statistics S, lookup_actions LAP, cash_limit CL, player P
          where LAP.id_action = S.id_action_p
          and CL.id_limit = S.id_limit
          and P.id_player = S.id_player
          and P.player_name = '%PLAYER_NAME%'"""

conn = psycopg2.connect(DB)
cur = conn.cursor(cursor_factory = psycopg2.extras.NamedTupleCursor)

class Hud(tk.Toplevel):
  def __init__(self,parent,player,seat,table):
    tk.Toplevel.__init__(self,parent)
    self.player = player
    self.seat = seat
    self.table = table
    self.configure(background='black')
    self.overrideredirect(True)
    self.attributes("-topmost", True)
    self.wait_visibility(self)
    self.wm_attributes("-alpha", 0.8)
    self.text = tk.Text(self,height=2, wrap="word",bg="black",fg="white", font=("Roboto", 8))
    self.text.pack(side="top", fill="x")
    self.text.tag_configure("yellow", foreground="yellow")
    self.text.tag_configure("white", foreground="white")
    self.text.tag_configure("red", foreground="red")
    self.text.tag_configure("blue", foreground="blue")
    self.text.tag_configure("green", foreground="green")   
    #self.label1 = tk.Label(self, bg='black',fg='white', font=("Roboto", 8))
    #self.label2 = tk.Label(self, bg='black',fg='white', font=("Roboto", 8))
    #self.label1.grid(row=0,column=0)
    #self.label2.grid(row=1,column=0)
    #self.label1.pack(side="right", fill="both", expand=True)
  def Update(self,stats):
    X,Y,W,H = get_win_position(self.table)
    x,y = get_hud_position(self.seat,X,Y,W,H)
    self.geometry('100x40+'+str(x)+'+'+str(y))
    self.stats=stats
    self.text.delete(1.0, tk.END)
    self.text.insert("end", self.player[:3]+': ' ,"white")
    self.text.insert("end", '{:2.0f}'.format(stats['vpip']) ,"yellow")
    self.text.insert("end", ' / ' ,"white")
    self.text.insert("end", '{:2.0f}'.format(stats['pfr']) ,"yellow")
    self.text.insert("end", ' / ' ,"white")
    self.text.insert("end", '{:2.0f}\n'.format(stats['3Bet']) ,"blue")
    self.text.insert("end", '{:2.0f}'.format(stats['CBet']) ,"green")
    self.text.insert("end", ' / ' ,"white")
    self.text.insert("end", '{:2.0f}'.format(stats['CBetF']) ,"green")
    self.text.insert("end", ' / ' ,"white")
    self.text.insert("end", '({:2.0f})'.format(stats['hands']) ,"red")
    #self.label1.configure(text=stats_to_str(self.stats,1))
    #self.label2.configure(text=stats_to_str(self.stats,2))

def get_win_position(name):
  id = getoutput("xdotool search --name '"+name+"'")
  lines=getoutput("xwininfo -id "+id).split("\n")
  if lines[0].find("error")>0:
    return (0,0,0,0)
  for line in lines:
    if line.find("Absolute upper-left X")>0:
      X=int(line.split(":")[1])
    if line.find("Absolute upper-left Y")>0:
      Y=int(line.split(":")[1])
    if line.find("Width")>0:
      W=int(line.split(":")[1])
    if line.find("Height")>0:
      H=int(line.split(":")[1])
  return X,Y,W,H

def get_hud_position(seat,X,Y,W,H):
  x=y=0
  if seat == 2:
    x=X
    y=Y+35
  elif seat == 3:
    x=X+W*0.55
    y=Y-10
  elif seat == 4:
    x=X+W-100
    y=Y+H*0.4
  elif seat == 0:
    x=X+W*0.15
    y=Y+H*0.75
  elif seat == 1:
    x=X
    y=Y+H*0.4
  return int(x),int(y)

def divide(a,b):
  if b==0:
    return 0.0
  else:
    return a/b

def stats_to_str(stats,type):
  if type==0:
    return '{:2.0f}'.format(stats['vpip']) + ' / ' + \
      '{:2.0f}'.format(stats['pfr']) + ' / ' + \
      '{:2.0f}'.format(stats['3Bet']) + ' / ' + \
      '{:2.0f}'.format(stats['CBet']) + ' / ' + \
      '{:2.0f}'.format(stats['CBetF']) + ' / (' + \
      '{:2.0f}'.format(stats['hands']) + ')'
  if type==1:
    return '{:2.0f}'.format(stats['vpip']) + ' / ' + \
      '{:2.0f}'.format(stats['pfr']) + ' / ' + \
      '{:2.0f}'.format(stats['3Bet'])
  if type==2:
    return '{:2.0f}'.format(stats['CBet']) + ' / ' + \
      '{:2.0f}'.format(stats['CBetF']) + ' / (' + \
      '{:2.0f}'.format(stats['hands']) + ')'

def get_stats(player):
  cur.execute(SQL_GET_STATS.replace('%PLAYER_NAME%',player))
  res = cur.fetchone()
  stats={'vpip':divide(res.cnt_vpip , (res.cnt_hands - res.cnt_walks)) * 100,
    'pfr':divide(res.cnt_pfr , res.cnt_pfr_opp) * 100,
    '3Bet':divide(res.cnt_p_3bet , res.cnt_p_3bet_opp) * 100,
    'CBet':divide(res.cnt_f_cbet , res.cnt_f_cbet_opp) * 100,
    'CBetF':divide(res.cnt_f_cbet_def_action_fold , res.cnt_f_cbet_def_opp) * 100,
    'hands':res.cnt_hands}  
  return stats

huds=[]
root = tk.Tk()
button = tk.Button (root, text = "Good-bye.", command = root.destroy)
button.pack()

def tick():
  # get active players from DB (player, seat, table)
  cur.execute(SQL_GET_PLAYER)
  players = cur.fetchall()
  # create a HUD if not exist yet for this player/table
  for player in players:
    hasHud = False
    for hud in huds:
      if hud.player == player.player_name and hud.table == player.table_name:
        hasHud = True
    if not(hasHud):
      huds.append(Hud(root,player.player_name,(player.seat-player.myseat)%5,player.table_name))
  # for each HUD, check if it should be removed (because player not active anymore) or moved and update it with the stats
  for hud in huds:
    hasPlayer = False
    for player in players:
      if hud.player == player.player_name  and hud.table == player.table_name:
        hasPlayer = True
    if not(hasPlayer):
      hud.destroy()
      huds.remove(hud)
    else:
      # Move it if required and Update Stats
      stats=get_stats(hud.player)
      hud.Update(stats)
  root.after(2000, tick)

tick()
root.mainloop()
