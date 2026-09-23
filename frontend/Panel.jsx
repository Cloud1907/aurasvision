import { useState } from 'react';
import { useResource, useMotionAllowed } from './hooks/useResource';
import Icon from './components/Icon';
import { cameraName } from './components/panelData';
import CommandHeader from './components/CommandHeader';
import LiveCameraGrid from './components/LiveCameraGrid';
import Aurora from './react-bits/Aurora';
import Noise from './react-bits/Noise';
import PanelMetrics from './components/PanelMetrics';
import PanelAlerts from './components/PanelAlerts';
import PanelActivity from './components/PanelActivity';
import PanelCameras from './components/PanelCameras';
import PanelShortcuts, { ArchiveSummary } from './components/PanelShortcuts';
import AlertInspector from './components/AlertInspector';
import AnalyticsChart from './components/AnalyticsChart';

export default function Panel({ bridge }) {
  const motion = useMotionAllowed();
  const cameras = useResource(bridge, '/cameras', 30000);
  const health = useResource(bridge, '/health', 10000);
  const alarms = useResource(bridge, '/alerts?limit=500&pending=true', 10000);
  const status = useResource(bridge, '/status', 15000);
  // Grafik en fazla 12 dilim, akış 5 satır ister: 500 satırı 15 sn'de bir çekip serileştirmek israftı.
  const events = useResource(bridge, '/events?limit=200', 15000);
  const totals = useResource(bridge, '/events/summary?hours=24', 30000);
  const archive = useResource(bridge, '/recordings/stats', 60000);
  const capabilities = useResource(bridge, '/capabilities', 60000);
  const [selected, setSelected] = useState(null);
  const rows = cameras.data || [];
  const refresh = () => [cameras, health, alarms, status, events, totals, archive, capabilities].forEach(r => r.retry());
  return <div className="ops command-center" data-motion={motion ? 'on' : 'off'}>
    <div className="command-atmosphere"><Aurora motion={motion}/><Noise patternAlpha={13}/></div>
    <CommandHeader status={status} health={health} bridge={bridge}/>
    <PanelMetrics cameras={cameras} status={status} alarms={alarms} events={events} archive={archive}/>
    <AnalyticsChart events={events} cameras={cameras} totals={totals} capabilities={capabilities}/>
    <div className="command-workspace dashboard-layout"><div className="dashboard-main"><LiveCameraGrid cameras={cameras} bridge={bridge} alarms={alarms}/></div>
      <aside className="command-sidebar" aria-label="Aktif alarm ve olay akışı"><PanelAlerts alarms={alarms} rows={rows} bridge={bridge} onSelect={setSelected}/><PanelActivity events={events} rows={rows} bridge={bridge}/></aside>
    </div>
    <div className="command-lower"><PanelCameras cameras={cameras} health={health} bridge={bridge}/><PanelShortcuts bridge={bridge}/><ArchiveSummary archive={archive} bridge={bridge}/></div>
    <div className="ops-bottom"><span><span className="ops-mark"/> AURASVISION <span className="ops-caption">/ Görüntü analitiği</span></span><button className="ops-link" onClick={refresh}><Icon name="refresh" size={14}/> Verileri yenile</button></div>
    {selected && <AlertInspector alert={selected} cameraName={cameraName(rows, selected.camera_id)} bridge={bridge} onClose={() => setSelected(null)} onAccepted={() => { setSelected(null); alarms.retry(); bridge.refreshBadge(); }}/>}
  </div>;
}
