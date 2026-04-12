import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { UploadCloud, CheckCircle, AlertTriangle, Loader2 } from "lucide-react";
import { motion } from "framer-motion";

export default function Upload({ onUploadComplete }: { onUploadComplete: () => void }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;
    setUploading(true);
    setError(null);

    const formData = new FormData();
    acceptedFiles.forEach(file => formData.append("files", file));

    try {
      const res = await fetch("http://127.0.0.1:8000/api/upload", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Failed to upload files");
      }

      const data = await res.json();
      
      // Let UX breathe
      setTimeout(() => {
          setUploading(false);
          onUploadComplete();
      }, 1000);

    } catch (err: any) {
      setError(err.message || "An error occurred");
      setUploading(false);
    }
  }, [onUploadComplete]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    disabled: uploading
  });

  return (
    <div className="p-8 pb-10">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-2xl p-16 text-center cursor-pointer transition-all duration-300
          ${isDragActive ? "border-accent bg-accent/5 scale-[1.02]" : "border-zinc-700 hover:border-zinc-500 hover:bg-zinc-900"}
          ${uploading ? "opacity-50 pointer-events-none border-zinc-700" : ""}`}
      >
        <input {...getInputProps()} />
        <div className="w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6 bg-zinc-800 border border-zinc-700 shadow-inner">
          {uploading ? (
             <Loader2 className="w-8 h-8 text-accent animate-spin" />
          ) : (
             <UploadCloud className={`w-8 h-8 transition-colors ${isDragActive ? 'text-accent' : 'text-zinc-400'}`} />
          )}
        </div>
        <p className="text-xl font-medium text-zinc-200 mb-2">
          {uploading ? "Extracting & Vectorizing..." : (isDragActive ? "Drop the PDFs here..." : "Drag & drop PDFs here")}
        </p>
        <p className="text-zinc-500 text-sm">or click to browse your computer</p>
      </div>

      {error && (
        <motion.div initial={{opacity:0, y:-10}} animate={{opacity:1, y:0}} className="mt-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3 text-red-500 text-sm">
          <AlertTriangle size={18} />
          {error}
        </motion.div>
      )}
    </div>
  );
}
