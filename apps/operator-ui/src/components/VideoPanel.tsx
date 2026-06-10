import { useEffect, useRef } from "react";

interface VideoTileProps {
  label: string;
  stream: MediaStream | null;
}

function VideoTile({ label, stream }: VideoTileProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
  }, [stream]);

  return (
    <div className="video-tile">
      <video ref={videoRef} autoPlay playsInline muted />
      <div className="video-label">
        {label}
        {!stream && <span className="video-placeholder"> (no signal)</span>}
      </div>
    </div>
  );
}

export interface VideoPanelProps {
  gripper: MediaStream | null;
  global: MediaStream | null;
}

export function VideoPanel({ gripper, global }: VideoPanelProps) {
  return (
    <section className="panel video-panel">
      <VideoTile label="Gripper camera" stream={gripper} />
      <VideoTile label="Global camera" stream={global} />
    </section>
  );
}
