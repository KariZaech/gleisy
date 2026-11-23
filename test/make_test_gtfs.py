"""Synthetic GTFS in Swiss format (quoted, Parent ids, platform_code) around Brig - for testing only."""
import zipfile, csv, io
S = {  # name: (id, lat, lon)
 "Brig":("8501609",46.3195,7.9881), "Visp":("8501605",46.2937,7.8817), "Sion":("8501506",46.2275,7.3593),
 "Genève-Aéroport":("8501008",46.2321,6.1086), "Bern":("8507000",46.9490,7.4391), "Basel SBB":("8500010",47.5474,7.5896),
 "Romanshorn":("8506131",47.5652,9.3792), "Domodossola":("8301605",46.1150,8.2894), "Iselle di Trasquera":("8301604",46.2045,8.1855),
 "Bitsch":("8501660",46.3337,8.0122), "Andermatt":("8505162",46.6340,8.5939), "Monthey":("8501400",46.2540,6.9480),
 "Eyholz":("8501650",46.2972,7.9126), "Zermatt":("8501689",46.0243,7.7479), "Eggerberg":("8501607",46.3060,7.8800),
 "Milano Centrale":("8301700",45.4860,9.2040), "Lötschberg":("8507493",46.39,7.80),
}
stops=[["stop_id","stop_name","stop_lat","stop_lon","location_type","parent_station","platform_code"]]
for n,(i,la,lo) in S.items():
    stops.append([f"Parent{i}",n,la,lo,"1","",""])
    plats = range(1,10) if n=="Brig" else [1,2]
    for p in plats: stops.append([f"{i}:0:{p}",n,la,lo,"",f"Parent{i}",str(p)])
routes=[["route_id","agency_id","route_short_name","route_long_name","route_desc","route_type"],
 ["r_R","11","R","","R","106"],["r_IR90","11","IR90","","IR","103"],["r_IC8","11","IC8","","IC","102"],
 ["r_IC6","11","IC6","","IC","102"],["r_RE","33","RE","","RE","106"],["r_EC","11","EC","","EC","102"],["r_B","801","9","","B","700"]]
trips=[["route_id","service_id","trip_id","trip_headsign","trip_short_name","direction_id","block_id"]]
st=[["trip_id","arrival_time","departure_time","stop_id","stop_sequence"]]
def T(m): return f"{m//60:02d}:{m%60:02d}:00"
def add(tid,route,no,seq,block=""):
    # seq: list of (station, platform, arr_min, dep_min)
    trips.append([route,"TA",tid,seq[-1][0],no,"0",block])
    for k,(n,p,a,d) in enumerate(seq):
        st.append([tid,T(a),T(d),f"{S[n][0]}:0:{p}",str(k+1)])
for h in range(5,23):
    b=h*60
    # IR90 through? no: IR90 terminates/originates at Brig (Genève) on track 6
    add(f"ir_in_{h}","r_IR90",f"18{h:02d}",[("Genève-Aéroport",1,b-180,b-180),("Sion",1,b-30,b-29),("Visp",2,b-10,b-9),("Brig",6,b+2,b+2)])
    add(f"ir_out_{h}","r_IR90",f"17{h:02d}",[("Brig",6,b+26,b+26),("Visp",1,b+34,b+35),("Sion",2,b+55,b+56),("Genève-Aéroport",1,b+180,b+180)])
    # IC8 Romanshorn turnaround track 3, block id given
    add(f"ic_in_{h}","r_IC8",f"8{h:02d}",[("Romanshorn",1,b-200,b-200),("Bern",1,b-62,b-60),("Visp",1,b+3,b+4),("Brig",3,b+11,b+11)],block=f"blk{h}")
    add(f"ic_out_{h}","r_IC8",f"8{h+20:02d}",[("Brig",3,b+48,b+48),("Visp",2,b+56,b+57),("Bern",2,b+120,b+122),("Romanshorn",2,b+260,b+260)],block=f"blk{h}")
    # Regio Monthey <-> Brig through Brig to Bitsch? R terminates and turns on track 1
    add(f"r_in_{h}","r_R",f"62{h:02d}",[("Monthey",1,b-60,b-60),("Visp",1,b+15,b+16),("Brig",1,b+24,b+24)])
    add(f"r_out_{h}","r_R",f"61{h:02d}",[("Brig",1,b+37,b+37),("Visp",2,b+45,b+46),("Monthey",2,b+120,b+120)])
    # RE Bern-Domodossola through Brig track 9
    add(f"re_{h}","r_RE",f"42{h:02d}",[("Bern",1,b-55,b-55),("Eggerberg",1,b+10,b+11),("Brig",9,b+20,b+22),("Iselle di Trasquera",1,b+38,b+39),("Domodossola",1,b+50,b+50)])
    if h%2==0:
        add(f"ec_{h}","r_EC",f"3{h:02d}",[("Basel SBB",1,b-170,b-170),("Bern",1,b-100,b-98),("Visp",2,b+30,b+31),("Brig",4,b+40,b+44),("Domodossola",2,b+70,b+72),("Milano Centrale",1,b+150,b+150)])
    add(f"bus_{h}","r_B","",[("Brig",1,b+5,b+5),("Visp",1,b+30,b+30)])
cal=[["service_id","monday","tuesday","wednesday","thursday","friday","saturday","sunday","start_date","end_date"],["TA","1","1","1","1","1","1","1","20251214","20261212"]]
def w(rows):
    buf=io.StringIO(); csv.writer(buf,quoting=csv.QUOTE_ALL,lineterminator="\n").writerows(rows); return buf.getvalue()
with zipfile.ZipFile("test/test_gtfs.zip","w",zipfile.ZIP_DEFLATED) as z:
    z.writestr("stops.txt",w(stops));z.writestr("routes.txt",w(routes));z.writestr("trips.txt",w(trips))
    z.writestr("stop_times.txt",w(st));z.writestr("calendar.txt",w(cal));z.writestr("calendar_dates.txt",w([["service_id","date","exception_type"]]))
print("ok", len(trips)-1, "trips")
