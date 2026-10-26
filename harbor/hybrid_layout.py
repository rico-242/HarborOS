"""Independent mixed-size protected-group layout; not a Synology SHR format."""
MIB=1024**2
QUANTUM=256
HYBRID_LEVELS={
 'hybrid1':{'name':'Harbour Hybrid 1','minimum':2,'maximum':24,'description':'Mixed-size disks; one-drive protection. Grows by adding protected groups of at least two disks.'},
 'hybrid2':{'name':'Harbour Hybrid 2','minimum':4,'maximum':24,'description':'Mixed-size disks; two-drive protection. Grows by adding protected groups of at least four disks.'},
}

def layout(level,sizes):
 if level not in HYBRID_LEVELS:raise ValueError('Choose a hybrid protection level.')
 rule=HYBRID_LEVELS[level]
 if not rule['minimum']<=len(sizes)<=rule['maximum']:raise ValueError('Not enough disks for this hybrid protection level.')
 if any(type(size)!=int or size<512*MIB for size in sizes):raise ValueError('Hybrid disks must be at least 512 MiB.')
 usable=[((size//MIB-8)//QUANTUM)*QUANTUM for size in sizes]
 layers=[];lower=0;allocated=0;parity=1 if level=='hybrid1' else 2
 for upper in sorted(set(usable)):
  members=[i for i,size in enumerate(usable) if size>=upper]
  if len(members)<rule['minimum']:break
  component=(upper-lower-8)*1024
  raid='1' if parity==1 and len(members)==2 else '5' if parity==1 else '6'
  capacity=component*1024*(len(members)-parity)
  layers.append({'members':members,'start_mib':lower+1,'end_mib':upper+1,'component_kib':component,'raid':raid,'capacity':capacity})
  allocated+=(upper-lower)*len(members)*MIB;lower=upper
 return {'level':level,'layers':layers,'capacity':sum(t['capacity'] for t in layers),
         'unallocated':sum(usable)*MIB-allocated,'alignment_and_reserved':sum(sizes)-sum(usable)*MIB,
         'protection':parity,'expansion_minimum':rule['minimum']}

def mirror_capacity(sizes):
 if len(sizes)<2:return 0
 return min(sum(sizes)//2,sum(sizes)-max(sizes))
