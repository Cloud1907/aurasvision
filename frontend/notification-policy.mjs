// Olay tekilleştirme görsel bileşen ömründen bağımsızdır.
export class NotificationPolicy {
  constructor(){this.seen=new Set();this.last=new Map();}
  accept(alert,rules,now=Date.now()){
    if(this.seen.has(alert.id))return null;
    this.seen.add(alert.id);
    if(this.seen.size>5000)this.seen.delete(this.seen.values().next().value);
    if(alert.acked_at)return null;
    const kind=alert.kind==='fire_warning'?'fire':alert.kind;
    const matches=rules.filter(r=>r.enabled&&r.camera_id===alert.camera_id&&r.kind===kind&&
      (!this.last.has(r.id)||now-this.last.get(r.id)>=r.cooldown*1000));
    if(!matches.length)return null;
    matches.forEach(r=>this.last.set(r.id,now));
    return {...alert,popup:matches.some(r=>r.popup),sound:matches.some(r=>r.sound),
      tone:matches.some(r=>r.sound&&r.tone==='urgent')?'urgent':'soft'};
  }
}
