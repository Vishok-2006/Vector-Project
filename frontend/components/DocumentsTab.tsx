"use client";

import { useState, useEffect } from "react";
import { Upload, FileText, CheckCircle2, AlertCircle, Loader2, Trash2 } from "lucide-react";
import { useDropzone } from "react-dropzone";

interface Document {
  id: number;
  filename: string;
  status: string;
  created_at: string;
}

export default function DocumentsTab() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/documents");
      const data = await res.json();
      setDocuments(data);
    } catch (error) {
      console.error("Failed to fetch documents", error);
    }
  };

  const onDrop = async (acceptedFiles: File[]) => {
    setUploading(true);
    const formData = new FormData();
    acceptedFiles.forEach((file) => formData.append("files", file));

    try {
      await fetch("http://localhost:8000/api/upload", {
        method: "POST",
        body: formData,
      });
      fetchDocuments();
    } catch (error) {
      console.error("Upload failed", error);
    } finally {
      setUploading(false);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
  });

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <div 
        {...getRootProps()} 
        className={`border-2 border-dashed rounded-2xl p-12 text-center transition-all cursor-pointer ${isDragActive ? 'border-indigo-500 bg-indigo-500/5' : 'border-zinc-800 hover:border-zinc-700 bg-zinc-900/30'}`}
      >
        <input {...getInputProps()} />
        <div className="w-16 h-16 bg-zinc-800 rounded-2xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
          {uploading ? <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" /> : <Upload className="w-8 h-8 text-zinc-400" />}
        </div>
        <h3 className="text-xl font-bold text-white mb-2">
          {uploading ? 'Processing Documents...' : 'Upload Knowledge Assets'}
        </h3>
        <p className="text-zinc-500 max-w-sm mx-auto">
          Drag and drop PDF files here, or click to browse. We'll automatically vectorize and index them.
        </p>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between mb-2 px-2">
           <h2 className="text-sm font-bold text-zinc-500 uppercase tracking-widest">Indexed Knowledge ({documents.length})</h2>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {documents.map((doc) => (
            <div 
              key={doc.id}
              className="p-4 bg-zinc-900/50 border border-zinc-800 rounded-xl flex items-center gap-4 group"
            >
              <div className="w-10 h-10 rounded-lg bg-zinc-800 flex items-center justify-center text-zinc-400">
                <FileText size={20} />
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-medium text-white truncate">{doc.filename}</h4>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[10px] text-zinc-500 font-mono">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </span>
                  <div className="w-1 h-1 rounded-full bg-zinc-700" />
                  <span className={`text-[10px] font-bold uppercase tracking-widest ${doc.status === 'success' ? 'text-emerald-500' : 'text-rose-500'}`}>
                    {doc.status}
                  </span>
                </div>
              </div>
              <button className="opacity-0 group-hover:opacity-100 p-2 text-zinc-600 hover:text-rose-400 transition-all">
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          {documents.length === 0 && !uploading && (
            <div className="col-span-full py-12 text-center bg-zinc-900/20 border border-zinc-900 border-dashed rounded-2xl">
              <p className="text-zinc-600 italic">No documents indexed yet.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
