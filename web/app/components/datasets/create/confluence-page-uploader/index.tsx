import React, { useState } from 'react'
import { useContext } from 'use-context-selector'
import { v4 as uuid4 } from 'uuid'
import s from './index.module.css' // 引入样式文件
import type { ConfluencePage, FileItem } from '@/models/datasets'
import { upload } from '@/service/base'
import { ToastContext } from '@/app/components/base/toast'
import cn from '@/utils/classnames'

type ConfluencePageUploaderProps = {
  confluencePageList: ConfluencePage[] // 当前的 Confluence 页面列表
  onConfluenceListUpdate: (pages: ConfluencePage[]) => void // Confluence 页面列表变化回调
}

const ConfluencePageUploader: React.FC<ConfluencePageUploaderProps> = ({
  confluencePageList,
  onConfluenceListUpdate,
}) => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { notify } = useContext(ToastContext)
  const [urls, setUrls] = useState<string[]>([]) // 存储用户输入的URLs
  const [inputValue, setInputValue] = useState('') // 输入框的值

  // 获取文件类型
  const getFileType = (file: File) => {
    const arr = file.name.split('.')
    return arr[arr.length - 1]
  }

  // 获取文件大小
  const getFileSize = (size: number) => {
    if (size / 1024 < 10)
      return `${(size / 1024).toFixed(2)}KB`
    return `${(size / 1024 / 1024).toFixed(2)}MB`
  }

  // 文件上传逻辑
  const fileUpload = async (
    fileItem: FileItem,
    pageList: ConfluencePage[],
    pageIndex: number,
  ): Promise<void> => {
    const formData = new FormData()
    formData.append('file', fileItem.file)

    const onProgress = (e: ProgressEvent) => {
      if (e.lengthComputable) {
        const percent = Math.floor((e.loaded / e.total) * 100)
        // 更新文件上传进度
        const updatedFileItem = { ...fileItem, progress: percent }
        const updatedPageList = pageList.map((page, index) =>
          index === pageIndex
            ? {
              ...page,
              children: page.children.map(item =>
                item.fileID === fileItem.fileID ? updatedFileItem : item,
              ),
            }
            : page,
        )
        onConfluenceListUpdate(updatedPageList) // 触发页面列表变化回调
      }
    }

    try {
      const response = await upload({
        xhr: new XMLHttpRequest(),
        data: formData,
        onprogress: onProgress,
      }, false, undefined, '?source=datasets')

      if (response) {
        // 上传成功，更新文件项
        const updatedFileItem = {
          ...fileItem,
          progress: 100,
          file: response, // 更新文件对象
        }
        const updatedPageList = pageList.map((page, index) =>
          index === pageIndex
            ? {
              ...page,
              children: page.children.map(item =>
                item.fileID === fileItem.fileID ? updatedFileItem : item,
              ),
            }
            : page,
        )
        onConfluenceListUpdate(updatedPageList) // 触发页面列表变化回调
      }
    }
    catch (err) {
      notify({ type: 'error', message: 'File upload failed' })
      console.error(err)

      // 上传失败，更新文件状态
      const updatedFileItem = { ...fileItem, progress: -2 }
      const updatedPageList = pageList.map((page, index) =>
        index === pageIndex
          ? {
            ...page,
            children: page.children.map(item =>
              item.fileID === fileItem.fileID ? updatedFileItem : item,
            ),
          }
          : page,
      )
      onConfluenceListUpdate(updatedPageList) // 触发页面列表变化回调
    }
  }

  // 删除文件
  const removeFile = (fileID: string, pageIndex: number) => {
    const updatedPageList = confluencePageList.map((page, index) =>
      index === pageIndex
        ? {
          ...page,
          children: page.children.filter(item => item.fileID !== fileID),
        }
        : page,
    )
    onConfluenceListUpdate(updatedPageList) // 触发页面列表变化回调
  }

  // 处理 Confluence URL 输入
  const handleUrlChange = async (url: string) => {
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

      // 获取纯文本内容
      const textContent = await response.text()

      // 将纯文本内容封装为 .txt 文件
      const blob = new Blob([textContent], { type: 'text/plain' })
      const file = new File([blob], `confluence-page-${pageId}.txt`, { type: 'text/plain' })

      const fileItem: FileItem = {
        fileID: uuid4(),
        file,
        progress: 0, // 初始进度为0
      }

      // 检查是否已经存在该页面
      const existingPageIndex = confluencePageList.findIndex(page => page.pageId === pageId)
      let updatedPageList: ConfluencePage[]

      if (existingPageIndex !== -1) {
        // 如果页面已存在，更新该页面的文件列表
        updatedPageList = confluencePageList.map((page, index) =>
          index === existingPageIndex
            ? { ...page, children: [...page.children, fileItem] }
            : page,
        )
      }
      else {
        // 如果页面不存在，创建一个新的 ConfluencePage
        const newPage: ConfluencePage = {
          pageId,
          space: '',
          title: '',
          children: [fileItem],
        }
        updatedPageList = [...confluencePageList, newPage]
      }

      // 更新页面列表
      onConfluenceListUpdate(updatedPageList)

      // 开始上传文件
      await fileUpload(fileItem, updatedPageList, existingPageIndex !== -1 ? existingPageIndex : updatedPageList.length - 1)
    }
    catch (err) {
      setError('Error converting Confluence page to Markdown')
      console.error(err)
    }
    finally {
      setLoading(false)
    }
  }

  // 处理输入框变化
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newUrl = e.target.value.trim()
    setInputValue(newUrl)
    if (newUrl && !urls.includes(newUrl)) {
      setUrls([...urls, newUrl])
      handleUrlChange(newUrl)
      setInputValue('')
    }
  }

  // 处理删除URL
  const handleRemoveUrl = (urlToRemove: string) => {
    setUrls(urls.filter(url => url !== urlToRemove))
  }

  return (
    <div className={s.confluencePageUploader}>
      <div className={s.inputContainer}>
        <div className={s.inputWithTags}>
          {urls.map((url, index) => (
            <div key={index} className={s.urlTag}>
              {url}
              <span className={s.removeTag} onClick={() => handleRemoveUrl(url)}>×</span>
            </div>
          ))}
          <input
            type="text"
            placeholder={urls.length === 0 ? "Enter Confluence Page URL" : ""}
            className={s.input}
            value={inputValue}
            onChange={handleInputChange}
            disabled={loading}
            style={{ width: '100%' }} // 调整输入框宽度
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
              {page.children.map((fileItem, fileIndex) => (
                <div
                  key={`${fileItem.fileID}-${fileIndex}`}
                  className={cn(
                    s.file,
                    fileItem.progress < 100 && s.uploading,
                  )}
                >
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
                          removeFile(fileItem.fileID, pageIndex) // 移除文件
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