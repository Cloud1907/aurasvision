import { motion } from 'motion/react';
import { useMotionAllowed } from '../hooks/useResource';
import './AnimatedList.css';

// React Bits uyarlaması: Tab tuşunu yakalamaz; kritik satırlar gecikmeden görünür.
export default function AnimatedList({ items = [], itemKey, renderItem }) {
  const allowed = useMotionAllowed();
  return <ul className="rb-animated-list">{items.map(item => <motion.li key={itemKey(item)}
    initial={false} whileHover={allowed ? { x: 2 } : undefined}
    transition={{ duration: allowed ? 0.16 : 0 }}>{renderItem(item)}</motion.li>)}</ul>;
}
