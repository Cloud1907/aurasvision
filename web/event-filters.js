/* Olay akışı filtreleri: tarihleri tarayıcının yerel saatinden UTC'ye çevir. */
(() => {
  const defaults = () => ({tur:'', kamera:'', q:'', start:'', end:'', offset:0});
  function query(values) {
    const f={...defaults(), ...values};
    const params=new URLSearchParams({limit:'51', offset:String(f.offset||0)});
    for(const key of ['tur','kamera','q'])if(f[key])params.set(key,f[key].trim());
    for(const key of ['start','end'])if(f[key]){
      const d=new Date(f[key]);
      if(Number.isNaN(d.getTime()))throw new Error('Geçerli bir tarih-saat girin.');
      params.set(key,d.toISOString());
    }
    if(f.start&&f.end&&new Date(f.start)>new Date(f.end))throw new Error('Başlangıç tarihi bitişten sonra olamaz.');
    return params.toString();
  }
  function localTime(date) {
    const local=new Date(date.getTime()-date.getTimezoneOffset()*60000);
    return local.toISOString().slice(0,16);
  }
  window.EventFilters={defaults,query,localTime};
})();
