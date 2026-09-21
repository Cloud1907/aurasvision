import { useState } from 'react';
import { useResource, useMotionAllowed } from './hooks/useResource';
import Icon from './components/Icon';
import { cameraName } from './components/panelData';
import CommandHeader from './components/CommandHeader';
import CameraStage from './components/CameraStage';
import Aurora from './react-bits/Aurora';
import Noise from './react-bits/Noise';
import PanelMetrics from './components/PanelMetrics';
import PanelAlerts from './components/PanelAlerts';
import PanelActivity from './components/PanelActivity';
import PanelCameras from './components/PanelCameras';
import PanelShortcuts, { ArchiveSummary } from './components/PanelShortcuts';
import AlertInspector from './components/AlertInspector';
import PanelTrend from './components/PanelTrend';

export default function Panel({ bridge }) {
  const motion = useMotionAllowed();
  const cameras = useResource(bridge, '/cameras', 30000);
  const health = useResource(bridge, '/health', 10000);
  const alarms = useResource(bridge, '/alerts?limit=50&pending=true', 10000);
  const status = useResource(bridge, '/status', 15000);
  const events = useResource(bridge, '/events?limit=5', 15000);
  const totals = useResource(bridge, '/events/summary?hours=24', 30000);
  const trend = useResource(bridge, '/events/trend?hours=24', 30000);
  const archive = useResource(bridge, '/recordings/stats', 60000);
  const [selected, setSelected] = useState(null);
  const [cameraId, setCameraId] = useState(null);
  const rows = cameras.data || [];
  const refresh = () => [cameras, health, alarms, status, events, totals, trend, archive].forEach(r => r.retry());
  const camera = rows.find(c => c.id === cameraId) || rows[0];
  return <div className="ops command-center" data-motion={motion ? 'on' : 'off'}>
    <div className="command-atmosphere"><Aurora motion={motion}/><Noise patternAlpha={13}/></div>
    <CommandHeader status={status} health={health} bridge={bridge}/>
    <PanelMetrics cameras={cameras} health={health} alarms={alarms} totals={totals}/>
    <div className="command-workspace"><CameraStage cameras={cameras} camera={camera} onCamera={setCameraId} bridge={bridge}/>
      <aside className="command-sidebar" aria-label="Olay ve kamera durumu"><PanelAlerts alarms={alarms} rows={rows} bridge={bridge} onSelect={setSelected}/>
        <PanelCameras cameras={cameras} health={health} bridge={bridge}/></aside>
      <PanelTrend trend={trend}/>
      <PanelActivity events={events} rows={rows} bridge={bridge}/>
    </div>
    <div className="command-lower"><PanelShortcuts bridge={bridge}/><ArchiveSummary archive={archive} bridge={bridge}/></div>
    <div className="ops-bottom"><span><span className="ops-mark"/> AURASVISION <span className="ops-caption">/ Görüntü analitiği</span></span><button className="ops-link" onClick={refresh}><Icon name="refresh" size={14}/> Verileri yenile</button></div>
    {selected && <AlertInspector alert={selected} cameraName={cameraName(rows, selected.camera_id)} bridge={bridge} onClose={() => setSelected(null)} onAccepted={() => { setSelected(null); alarms.retry(); bridge.refreshBadge(); }}/>}
  </div>;
}
