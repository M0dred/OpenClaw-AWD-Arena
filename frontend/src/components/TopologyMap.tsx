import React, { useEffect, useRef } from 'react';
import { Network, Options } from 'vis-network';

interface TopologyMapProps {
  playerCount: number;
  phase: string; // 'initializing', 'defense', 'attack', 'finished', etc.
}

const TopologyMap: React.FC<TopologyMapProps> = ({ playerCount, phase }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const nodes: any[] = [];
    const edges: any[] = [];

    const isAttack = phase === 'attack' || phase === 'finished';

    // Referee Engine / Arena Hub
    nodes.push({
      id: 'arena',
      label: isAttack ? 'Arena\nNetwork' : 'Referee\nEngine',
      shape: 'hexagon',
      color: {
        background: isAttack ? '#ef4444' : '#3b82f6', // red-500 / blue-500
        border: '#1e293b',
      },
      font: { color: '#ffffff', face: 'monospace' },
      size: 30,
    });

    for (let i = 1; i <= playerCount; i++) {
      // Agent Node
      nodes.push({
        id: `agent_${i}`,
        label: `Agent ${i}`,
        shape: 'box',
        color: {
          background: '#0ea5e9', // cyan-500
          border: '#0284c7',
        },
        font: { color: '#ffffff', face: 'monospace' },
      });

      // Target Node
      nodes.push({
        id: `target_${i}`,
        label: `Target ${i}`,
        shape: 'database',
        color: {
          background: '#10b981', // emerald-500
          border: '#059669',
        },
        font: { color: '#ffffff', face: 'monospace' },
      });

      if (isAttack) {
        // Attack phase: Everyone connects to Arena
        edges.push({
          from: `agent_${i}`,
          to: 'arena',
          color: { color: '#ef4444' }, // red line
          dashes: true,
        });
        edges.push({
          from: `target_${i}`,
          to: 'arena',
          color: { color: '#94a3b8' },
        });
      } else {
        // Defense phase: Isolated networks
        // Add a virtual switch for the isolated network
        nodes.push({
          id: `switch_${i}`,
          label: `Net ${i}`,
          shape: 'dot',
          size: 10,
          color: { background: '#64748b', border: '#475569' }, // slate-500
          font: { color: '#94a3b8', size: 12 },
        });

        edges.push({
          from: `agent_${i}`,
          to: `switch_${i}`,
          color: { color: '#0ea5e9' },
        });
        edges.push({
          from: `target_${i}`,
          to: `switch_${i}`,
          color: { color: '#10b981' },
        });
      }
    }

    const data = { nodes, edges };
    const options: Options = {
      physics: {
        enabled: true,
        barnesHut: {
          gravitationalConstant: -2000,
          centralGravity: 0.3,
          springLength: 100,
          springConstant: 0.04,
          damping: 0.09,
          avoidOverlap: 0.1
        },
      },
      interaction: {
        zoomView: true,
        dragView: true,
      },
      edges: {
        width: 2,
        smooth: {
          enabled: true,
          type: 'continuous',
          roundness: 0.5,
        },
      },
    };

    if (networkRef.current) {
      networkRef.current.setData(data);
    } else {
      networkRef.current = new Network(containerRef.current, data, options);
    }

    return () => {
      // Clean up on unmount is handled if needed, 
      // but keeping networkRef prevents memory leaks if we destroy it
      // networkRef.current?.destroy(); 
      // networkRef.current = null;
    };
  }, [playerCount, phase]);

  // Handle cleanup separately to avoid re-creating on every render
  useEffect(() => {
    return () => {
      if (networkRef.current) {
        networkRef.current.destroy();
        networkRef.current = null;
      }
    };
  }, []);

  return (
    <div className="w-full h-full min-h-[300px] bg-slate-900/50 rounded-md border border-slate-700 relative">
      <div ref={containerRef} className="absolute inset-0" />
      <div className="absolute top-2 left-2 flex gap-2 pointer-events-none">
        <div className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-cyan-500 inline-block"></span>
          <span className="text-xs text-slate-300 font-mono">Agent</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-emerald-500 inline-block"></span>
          <span className="text-xs text-slate-300 font-mono">Target</span>
        </div>
      </div>
    </div>
  );
};

export default TopologyMap;
