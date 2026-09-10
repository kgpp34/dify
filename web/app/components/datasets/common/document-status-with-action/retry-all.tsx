'use client'
import type { FC } from 'react'
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RiLoopLeftLine } from '@remixicon/react'
import Button from '@/app/components/base/button'
import Confirm from '@/app/components/base/confirm'
import Toast from '@/app/components/base/toast'
import { retryAllDocs } from '@/service/datasets'

type Props = {
  datasetId: string
  onSuccess?: () => void
}

const RetryAllButton: FC<Props> = ({ datasetId, onSuccess }) => {
  const { t } = useTranslation()
  const [showConfirm, setShowConfirm] = useState(false)
  const [isRetrying, setIsRetrying] = useState(false)

  const onConfirm = async () => {
    setIsRetrying(true)
    try {
      const res = await retryAllDocs({ datasetId })
      Toast.notify({ type: 'success', message: t('dataset.retryAllSuccess', { count: res.count }) })
      onSuccess?.()
    }
    catch {
      Toast.notify({ type: 'error', message: t('dataset.retryAllError') })
    }
    finally {
      setIsRetrying(false)
      setShowConfirm(false)
    }
  }

  return (
    <>
      <Button variant='secondary' className='shrink-0' onClick={() => setShowConfirm(true)}>
        <RiLoopLeftLine className='mr-1 size-4' />
        {t('dataset.retryAll')}
      </Button>
      {showConfirm && (
        <Confirm
          isShow={showConfirm}
          isLoading={isRetrying}
          isDisabled={isRetrying}
          title={t('dataset.retryAllConfirmTitle')}
          content={t('dataset.retryAllConfirmContent')}
          confirmText={t('common.operation.sure') as string}
          onConfirm={onConfirm}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </>
  )
}
export default RetryAllButton
