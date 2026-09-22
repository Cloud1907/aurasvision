import Icon from './Icon';

export default function QueueProgress({ hasPreviousData = false }) {
  return <div className="queue-progress" role="status" aria-live="polite" aria-label="Alarm kuyruğu güncelleniyor">
    <div className="queue-progress-title"><span className="queue-progress-spark" aria-hidden="true">✦</span><strong>Alarm kuyruğu güncelleniyor</strong></div>
    <ol>
      <li className="complete"><Icon name="check" size={14}/><span>{hasPreviousData ? 'Mevcut sonuçlar korundu' : 'Bağlantı kuruldu'}</span></li>
      <li className="active"><i aria-hidden="true"/><span>Yeni alarmlar alınıyor</span></li>
      <li className="queued"><i aria-hidden="true"/><span>Filtre sonucu hazırlanacak</span></li>
    </ol>
  </div>;
}
