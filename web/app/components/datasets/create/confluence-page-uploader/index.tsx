import React, { useCallback, useEffect, useState } from 'react'
import { useContext } from 'use-context-selector'
import { v4 as uuid4 } from 'uuid'
import s from './index.module.css'
import type { ConfluencePage, FileItem } from '@/models/datasets'
import { ToastContext } from '@/app/components/base/toast'
import cn from '@/utils/classnames'
import { upload } from '@/service/base'

type ConfluencePageUploaderProps = {
  confluencePageList: ConfluencePage[]
  onConfluenceListUpdate: (pages: ConfluencePage[]) => void
}

const ConfluencePageUploader: React.FC<ConfluencePageUploaderProps> = ({
  confluencePageList,
  onConfluenceListUpdate,
}) => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { notify } = useContext(ToastContext)
  const [urls, setUrls] = useState<string[]>([])
  const [inputValue, setInputValue] = useState('')

  useEffect(() => {
    console.log('confluencePageList updated:', confluencePageList)
  }, [confluencePageList])

  // 获取文件类型
  const getFileType = useCallback((file: File) => {
    const arr = file.name.split('.')
    return arr[arr.length - 1]
  }, [])

  // 获取文件大小
  const getFileSize = useCallback((size: number) => {
    if (size / 1024 < 10)
      return `${(size / 1024).toFixed(2)}KB`
    return `${(size / 1024 / 1024).toFixed(2)}MB`
  }, [])

  // 单个文件上传逻辑
  const fileUpload = useCallback(
    (fileItem: FileItem, pageIndex: number) => {
      const formData = new FormData()
      formData.append('file', fileItem.file)

      const onProgress = (e: ProgressEvent) => {
        if (e.lengthComputable) {
          const percent = Math.floor((e.loaded / e.total) * 100)
          console.log(`File ${fileItem.file.name} progress: ${percent}%`)

          // 更新进度
          const updatedPageList = confluencePageList.map((page, idx) =>
            idx === pageIndex
              ? {
                ...page,
                children: page.children.map(child =>
                  child.fileID === fileItem.fileID
                    ? { ...child, progress: percent } // 只更新目标文件的进度
                    : child, // 其他文件保持不变
                ),
              }
              : page,
          )
          onConfluenceListUpdate(updatedPageList)
        }
      }

      // 使用 then 和 catch 处理上传逻辑
      upload(
        {
          xhr: new XMLHttpRequest(),
          data: formData,
          onprogress: onProgress,
        },
        false,
        undefined,
        '?source=datasets',
      )
        .then((response) => {
          // 上传成功后，更新文件状态
          const updatedFileItem = {
            ...fileItem,
            progress: 100,
            file: response, // 确保 response 被正确保存
          }

          const updatedPageList = confluencePageList.map((page, idx) =>
            idx === pageIndex
              ? {
                ...page,
                children: page.children.map(child =>
                  child.fileID === fileItem.fileID
                    ? updatedFileItem // 更新目标文件为完成状态
                    : child, // 其他文件保持不变
                ),
              }
              : page,
          )
          onConfluenceListUpdate(updatedPageList)
        })
        .catch((err) => {
          console.error(err)
          notify({ type: 'error', message: 'File upload failed' })

          // 上传失败后，更新文件状态
          const updatedFileItem = { ...fileItem, progress: -2 }
          const updatedPageList = confluencePageList.map((page, idx) =>
            idx === pageIndex
              ? {
                ...page,
                children: page.children.map(child =>
                  child.fileID === fileItem.fileID
                    ? updatedFileItem // 更新目标文件为失败状态
                    : child, // 其他文件保持不变
                ),
              }
              : page,
          )
          onConfluenceListUpdate(updatedPageList)
        })
    },
    [confluencePageList, notify, onConfluenceListUpdate],
  )

  // 删除文件
  const removeFile = useCallback(
    (fileID: string, pageIndex: number) => {
      const updatedPageList = confluencePageList.map((page, idx) =>
        idx === pageIndex
          ? {
            ...page,
            children: page.children.filter(item => item.fileID !== fileID),
          }
          : page,
      )
      onConfluenceListUpdate(updatedPageList)
    },
    [confluencePageList, onConfluenceListUpdate],
  )

  // 处理 Confluence URL 输入
  const handleUrlChange = useCallback(
    async (url: string) => {
      const pageIdMatch = url.match(/pageId=(\d+)/)
      if (!pageIdMatch) {
        notify({ type: 'error', message: 'Invalid Confluence Page URL' })
        return
      }

      const pageId = pageIdMatch[1]

      setLoading(true)
      setError(null)

      try {
        const response = await fetch(`/confluence2md/page/${pageId}`)
        if (!response.ok)
          throw new Error('Failed to convert Confluence page to Markdown')

        const textContent = await response.text()
        const sections = textContent.split(/<!--\s*Page:\s*(.*?)\s*-->/)
        const files: { name: string; content: string }[] = []
        for (let i = 1; i < sections.length; i += 2) {
          const name = sections[i].trim()
          const content = sections[i + 1].trim()
          if (name && content)
            files.push({ name, content })
        }

        const existingPageIndex = confluencePageList.findIndex(page => page.pageId === pageId)
        const newFiles = files.map(file => ({
          fileID: uuid4(),
          file: new File([file.content], `${file.name}.txt`, { type: 'text/plain' }),
          progress: 0,
        }))

        const updatedPageList
          = existingPageIndex !== -1
            ? confluencePageList.map((page, idx) =>
              idx === existingPageIndex
                ? {
                  ...page,
                  children: [...page.children, ...newFiles],
                }
                : page,
            )
            : [
              ...confluencePageList,
              {
                pageId,
                space: '',
                title: '',
                children: newFiles,
              },
            ]
        onConfluenceListUpdate(updatedPageList)

        // 逐个上传文件
        const targetPageIndex = existingPageIndex !== -1 ? existingPageIndex : confluencePageList.length
        for (const fileItem of newFiles)
          fileUpload(fileItem, targetPageIndex)
      }
      catch (err) {
        setError('Error converting Confluence page to Markdown')
        console.error(err)
      }
      finally {
        setLoading(false)
      }
    },
    [confluencePageList, notify, onConfluenceListUpdate, fileUpload],
  )

  // 处理输入框变化
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newUrl = e.target.value.trim()
      setInputValue(newUrl)
      if (newUrl && !urls.includes(newUrl)) {
        setUrls([...urls, newUrl])
        handleUrlChange(newUrl)
        setInputValue('')
      }
    },
    [handleUrlChange, urls],
  )

  // 处理删除URL
  const handleRemoveUrl = useCallback(
    (urlToRemove: string) => {
      setUrls(urls.filter(url => url !== urlToRemove))
    },
    [urls],
  )

  return (
    <div className={s.confluencePageUploader}>
      <div className={s.inputContainer}>
        <div className={s.inputWithTags}>
          {urls.map((url, index) => (
            <div key={index} className={s.urlTag}>
              {url}
              <span className={s.removeTag} onClick={() => handleRemoveUrl(url)}>
                ×
              </span>
            </div>
          ))}
          <input
            type="text"
            placeholder={urls.length === 0 ? 'Enter Confluence Page URL' : ''}
            className={s.input}
            value={inputValue}
            onChange={handleInputChange}
            disabled={loading}
            style={{ width: '100%' }}
          />
        </div>
        {loading && <div className={s.loadingSpinner} />}
      </div>
      {error && <div className={s.errorMessage}>{error}</div>}

      {/* 文件列表 */}
      <div className={s.fileList}>
        {confluencePageList.map((page, pageIndex) => (
          <div key={page.pageId} className={s.pageContainer}>
            <div className={s.fileList}>
              {page.children.map(fileItem => (
                <div key={fileItem.fileID} className={cn(s.file, fileItem.progress < 100 && s.uploading)}>
                  {fileItem.progress < 100 && (
                    <div className={s.progressbar} style={{ width: `${fileItem.progress}%` }} />
                  )}
                  <div className={s.fileInfo}>
                    <div className={cn(s.fileIcon, s[getFileType(fileItem.file)])} />
                    <div className={s.filename}>{fileItem.file.name}</div>
                    <div className={s.size}>{getFileSize(fileItem.file.size)}</div>
                  </div>
                  <div className={s.actionWrapper}>
                    {fileItem.progress < 100 && fileItem.progress >= 0 && (
                      <div className={s.percent}>{`${fileItem.progress}%`}</div>
                    )}
                    {fileItem.progress === 100 && (
                      <div
                        className={s.remove}
                        onClick={(e) => {
                          e.stopPropagation()
                          removeFile(fileItem.fileID, pageIndex)
                        }}
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default ConfluencePageUploader
