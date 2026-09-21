import Icon from './Icon';
export default function ResourceState({ resource, children, empty = false, emptyText = 'Henüz veri yok.' }) {
  if (resource.error) return <div className="ops-error" role="status"><Icon name="alert"/>
    <span>{resource.data ? 'Veriler güncel olmayabilir. ' : ''}{resource.error}</span>
    <button onClick={resource.retry}>Yeniden dene</button></div>;
  if (resource.data === null) return <div className="ops-skeleton" role="status" aria-label="Yükleniyor"><i/><i/><i/></div>;
  if (empty) return <div className="ops-empty"><Icon name="check" size={25}/><strong>{emptyText}</strong><span>Yeni bilgi geldiğinde burada görünecek.</span></div>;
  return children;
}
