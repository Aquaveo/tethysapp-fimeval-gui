// reactapp/src/Dropzone.tsx
import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import './Dropzone.css';

interface DropzoneProps {
  label: string;
  multiple: boolean;
  accept: string[]; // lowercase extensions, e.g. ['.tif', '.tiff']
  onAccepted: (files: File[]) => void;
}

function Dropzone({ label, multiple, accept, onAccepted }: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [rejected, setRejected] = useState(false);

  const isAccepted = (file: File) =>
    accept.some((ext) => file.name.toLowerCase().endsWith(ext));

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const files = Array.from(fileList);
    const good = files.filter(isAccepted);
    setRejected(good.length !== files.length);
    if (good.length > 0) onAccepted(good);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
    e.target.value = ''; // allow re-selecting the same file
  };

  return (
    <div className="dropzone-wrap">
      <div
        className={`dropzone ${dragOver ? 'dropzone--over' : ''}`}
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <span className="dropzone-arrow">&#8595;</span>
        <span className="dropzone-label">
          {label} or <span className="dropzone-browse">browse</span>
        </span>
        <input
          ref={inputRef}
          type="file"
          className="dropzone-input"
          multiple={multiple}
          accept={accept.join(',')}
          onChange={onChange}
        />
      </div>
      {rejected && (
        <p className="dropzone-error">Only {accept.join('/')} files are accepted</p>
      )}
    </div>
  );
}

export default Dropzone;
